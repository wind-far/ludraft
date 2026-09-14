"""Durable accounting with optional budget enforcement.

Amounts are integer millionths of CNY. Unknown provider outcomes keep their
reservation until explicitly reconciled; restarting never releases money.
"""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path


class BudgetError(ValueError):
    pass


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError
        return int((amount * 1_000_000).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, ValueError, TypeError):
        raise BudgetError('费用必须是非负的人民币金额') from None


def connection_key(config):
    # Deliberately exclude credentials and user prompts from the ledger.
    value = {k: config[k] for k in ('provider', 'base_url', 'model')}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def token_cost(inputs, outputs, input_rate, output_rate):
    if any(type(v) is not int or v < 0 for v in (inputs, outputs, input_rate, output_rate)):
        raise BudgetError('Token 数与价格必须是非负整数')
    return (inputs * input_rate + outputs * output_rate + 999_999) // 1_000_000


class BudgetLedger:
    def __init__(self, root: Path):
        self.path = Path(root) / 'budget.sqlite3'

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS policy (
                    id INTEGER PRIMARY KEY CHECK(id=1), cap INTEGER NOT NULL,
                    image_limit INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS prices (
                    identity TEXT PRIMARY KEY, input_rate INTEGER NOT NULL,
                    output_rate INTEGER NOT NULL, source TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS calls (
                    id TEXT PRIMARY KEY, identity TEXT NOT NULL, kind TEXT NOT NULL,
                    label TEXT NOT NULL, reserved INTEGER NOT NULL, actual INTEGER,
                    input_rate INTEGER NOT NULL, output_rate INTEGER NOT NULL,
                    input_limit INTEGER NOT NULL, output_limit INTEGER NOT NULL,
                    state TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            ''')
            self.path.chmod(0o600)
            con.execute('BEGIN IMMEDIATE')
            # Upgrade existing ledgers without rewriting their prices or calls.
            for table, additions in {
                'policy': {'enforce_limits': 'INTEGER NOT NULL DEFAULT 1'},
                'calls': {'priced': 'INTEGER NOT NULL DEFAULT 1',
                          'prompt_tokens': 'INTEGER', 'completion_tokens': 'INTEGER'},
            }.items():
                columns = {row['name'] for row in con.execute(f'PRAGMA table_info({table})')}
                for name, definition in additions.items():
                    if name not in columns:
                        con.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    @property
    def enabled(self):
        if not self.path.exists():
            return False
        with self.transaction() as con:
            return con.execute('SELECT 1 FROM policy WHERE id=1').fetchone() is not None

    def configure(self, cap_cny='100', image_limit=10):
        cap = money(cap_cny)
        if cap == 0 or type(image_limit) is not int or image_limit < 0:
            raise BudgetError('预算必须大于零，图片尝试上限必须是非负整数')
        with self.transaction() as con:
            # Configuration never resets accumulated spending or attempts.
            con.execute('''INSERT INTO policy(id,cap,image_limit,enforce_limits) VALUES(1,?,?,1)
                ON CONFLICT(id) DO UPDATE SET cap=excluded.cap,image_limit=excluded.image_limit,enforce_limits=1''', (cap, image_limit))

    def unlimited(self):
        """Keep accounting and history, but remove local cost and attempt caps."""
        with self.transaction() as con:
            con.execute('''INSERT INTO policy(id,cap,image_limit,enforce_limits) VALUES(1,0,0,0)
                ON CONFLICT(id) DO UPDATE SET enforce_limits=0''')

    def set_price(self, identity, input_cny_per_million, output_cny_per_million, source):
        if not source or len(source) > 1000:
            raise BudgetError('请记录实际价格的依据')
        with self.transaction() as con:
            con.execute('INSERT OR REPLACE INTO prices VALUES(?,?,?,?)',
                        (identity, money(input_cny_per_million), money(output_cny_per_million), source))

    def model_price(self, config):
        if not self.path.exists():
            return None
        with self.transaction() as con:
            row = con.execute('SELECT input_rate,output_rate FROM prices WHERE identity=?',
                              (connection_key(config),)).fetchone()
            return {'input_cny_per_million': row['input_rate']/1_000_000,
                    'output_cny_per_million': row['output_rate']/1_000_000} if row else None

    def reserve_model(self, config, inputs, outputs, label, request_id=None):
        identity = connection_key(config)
        with self.transaction() as con:
            price = con.execute('SELECT * FROM prices WHERE identity=?', (identity,)).fetchone()
            policy = con.execute('SELECT enforce_limits FROM policy WHERE id=1').fetchone()
            if price is None and (policy is None or policy['enforce_limits']):
                raise BudgetError('尚未配置该模型的实际价格，已阻止付费调用')
            input_rate, output_rate = (price['input_rate'], price['output_rate']) if price else (0, 0)
            amount = token_cost(inputs, outputs, input_rate, output_rate)
            return self._reserve(con, identity, 'model', amount, label, request_id,
                                 input_rate, output_rate, inputs, outputs, priced=price is not None)

    def reserve_image(self, identity, estimate_cny, label, request_id=None):
        with self.transaction() as con:
            return self._reserve(con, identity, 'image', money(estimate_cny), label, request_id)

    def _reserve(self, con, identity, kind, amount, label, request_id, input_rate=0, output_rate=0, inputs=0, outputs=0, priced=True):
        request_id = request_id or uuid.uuid4().hex
        values = (identity, kind, label, amount, input_rate, output_rate, inputs, outputs, int(priced))
        previous = con.execute('SELECT * FROM calls WHERE id=?', (request_id,)).fetchone()
        if previous:
            keys = ('identity', 'kind', 'label', 'reserved', 'input_rate', 'output_rate', 'input_limit', 'output_limit', 'priced')
            if tuple(previous[k] for k in keys) != values:
                raise BudgetError('同一请求标识不能用于不同的费用预留')
            return request_id
        policy = con.execute('SELECT * FROM policy WHERE id=1').fetchone()
        if policy is None:
            raise BudgetError('尚未启用实验预算')
        used = con.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM calls').fetchone()[0]
        if policy['enforce_limits'] and used + amount > policy['cap']:
            raise BudgetError('累计费用与预留已达到实验预算，已停止新调用')
        count = con.execute("SELECT COUNT(*) FROM calls WHERE kind='image'").fetchone()[0]
        if policy['enforce_limits'] and kind == 'image' and count >= policy['image_limit']:
            raise BudgetError('图片生成尝试已达到上限，失败尝试也计入')
        con.execute('''INSERT INTO calls(id,identity,kind,label,reserved,input_rate,output_rate,input_limit,output_limit,priced,state)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (request_id, *values, 'reserved' if priced else 'unpriced'))
        return request_id

    def finish_model(self, request_id, usage):
        with self.transaction() as con:
            row = con.execute('SELECT * FROM calls WHERE id=?', (request_id,)).fetchone()
            if row is None or row['kind'] != 'model':
                raise BudgetError('模型费用记录不存在')
            if row['actual'] is not None:
                return
            inputs, outputs = usage.get('prompt_tokens'), usage.get('completion_tokens')
            if any(type(v) is not int or v < 0 for v in (inputs, outputs)):
                con.execute('UPDATE calls SET state=? WHERE id=?', ('unknown' if row['priced'] else 'unpriced', request_id))
                return
            con.execute('UPDATE calls SET prompt_tokens=?,completion_tokens=? WHERE id=?', (inputs, outputs, request_id))
            if not row['priced']:
                # Missing prices mean unknown cost, never a free/settled call.
                con.execute("UPDATE calls SET state='unpriced' WHERE id=?", (request_id,))
                return
            actual = token_cost(inputs, outputs, row['input_rate'], row['output_rate'])
            con.execute("UPDATE calls SET actual=?,state='settled' WHERE id=?", (actual, request_id))

    def reconcile(self, request_id, actual_cny):
        # Explicit operator action after consulting the provider's bill.
        with self.transaction() as con:
            row = con.execute('SELECT actual FROM calls WHERE id=?', (request_id,)).fetchone()
            if row is None:
                raise BudgetError('费用记录不存在')
            if row['actual'] is not None:
                raise BudgetError('该记录已经核账，不能覆盖')
            con.execute("UPDATE calls SET actual=?,state='reconciled' WHERE id=?", (money(actual_cny), request_id))

    def summary(self):
        if not self.path.exists():
            return {'enabled': False}
        with self.transaction() as con:
            policy = con.execute('SELECT * FROM policy WHERE id=1').fetchone()
            if policy is None:
                return {'enabled': False}
            totals = con.execute('''SELECT COALESCE(SUM(actual),0),
                COALESCE(SUM(CASE WHEN actual IS NULL THEN reserved ELSE 0 END),0),
                COUNT(*), SUM(CASE WHEN kind='image' THEN 1 ELSE 0 END),
                SUM(CASE WHEN actual IS NULL THEN 1 ELSE 0 END),
                SUM(CASE WHEN priced=0 AND actual IS NULL THEN 1 ELSE 0 END) FROM calls''').fetchone()
            enforced = bool(policy['enforce_limits'])
            return {'enabled': True, 'enforce_limits': enforced, 'currency': 'CNY',
                    'cap_cny': policy['cap']/1_000_000 if enforced else None,
                    'settled_cny': totals[0]/1_000_000, 'held_cny': totals[1]/1_000_000,
                    'remaining_cny': max(0, policy['cap']-totals[0]-totals[1])/1_000_000 if enforced else None,
                    'over_budget': enforced and totals[0]+totals[1] > policy['cap'],
                    'calls': totals[2], 'image_attempts': totals[3] or 0,
                    'image_limit': policy['image_limit'] if enforced else None,
                    'unsettled_calls': totals[4] or 0, 'unpriced_calls': totals[5] or 0}

    def history(self):
        if not self.path.exists():
            return []
        with self.transaction() as con:
            return [dict(row) for row in con.execute('SELECT * FROM calls ORDER BY created,id')]

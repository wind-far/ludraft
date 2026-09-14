"""Configure an experiment budget without printing or requesting credentials."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio.budget import BudgetLedger, connection_key
from studio.llm import Gateway


def main():
    parser = argparse.ArgumentParser(description='游芽实验费用预留与核账（人民币）')
    parser.add_argument('--data', type=Path, default=Path(__file__).resolve().parents[1]/'.studio')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('history')
    commands.add_parser('unlimited', help='取消本地金额和图片尝试限制，保留用量及费用记录')
    configure = commands.add_parser('configure')
    configure.add_argument('--cap-cny', default='100')
    configure.add_argument('--image-limit', type=int, default=10)
    price = commands.add_parser('price')
    price.add_argument('--role', required=True, choices=['制作人','PM','策划','主程','程序','美术','UX','QA'])
    price.add_argument('--input-per-million', required=True)
    price.add_argument('--output-per-million', required=True)
    price.add_argument('--source', required=True, help='服务商价格页面或账户价格记录，不要填写凭据')
    reconcile = commands.add_parser('reconcile')
    reconcile.add_argument('--call-id', required=True)
    reconcile.add_argument('--actual-cny', required=True)
    args = parser.parse_args()
    ledger = BudgetLedger(args.data)
    if args.command == 'unlimited':
        ledger.unlimited()
    elif args.command == 'configure':
        ledger.configure(args.cap_cny, args.image_limit)
    elif args.command == 'price':
        config = Gateway(args.data).effective(args.role)
        if not config['model']:
            parser.error('请先在工作台配置该角色的模型')
        ledger.set_price(connection_key(config), args.input_per_million, args.output_per_million, args.source)
    elif args.command == 'reconcile':
        ledger.reconcile(args.call_id, args.actual_cny)
    print(json.dumps(ledger.history() if args.command == 'history' else ledger.summary(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

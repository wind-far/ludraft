---
# 注意不要修改本文头文件，如修改，CodeBuddy（内网版）将按照默认逻辑设置
type: manual
---
# 技能：C# 空安全最佳实践

> **领域**: csharp
> **适用Agent**: 程序 / 主程 / QA
> **加载时机**: 编码或审查涉及外部引用、组件获取、数据查找时按需加载
> **大小**: ~1.5KB

## 📌 核心知识

1. **Unity 的 null 特殊性**：UnityEngine.Object 重写了 `==` 和 `bool` 运算符，`Destroy` 后对象不是 C# 真正的 null，但 `== null` 返回 true
2. **?. 运算符陷阱**：`?.`（null条件运算符）对 Unity Object 不可靠，因为 Unity 重写了 `==` 但 `?.` 用的是 C# 原生 null 检查
3. **TryGetComponent > GetComponent**：`TryGetComponent` 不产生 GC，且返回值直接表示成功/失败
4. **集合操作**：LINQ 的 `FirstOrDefault` 可能返回 null（引用类型）或 default（值类型），必须区分处理
5. **字符串处理**：使用 `string.IsNullOrEmpty()` 或 `string.IsNullOrWhiteSpace()` 而非 `== null` 或 `== ""`

## ✅ 最佳实践

1. **组件获取**：使用 `TryGetComponent<T>(out var comp)` 替代 `GetComponent<T>() != null`
2. **外部引用**：所有 `[SerializeField]` 字段在使用前检查 null，或在 `OnValidate` 中验证
3. **事件触发**：使用 `event?.Invoke()` 或先检查 `if (event != null) event.Invoke()`
4. **Find/查找操作**：所有 `Find`、`FindObjectOfType`、字典 `TryGetValue` 的返回值都要检查
5. **Early Return 模式**：方法开头检查前置条件，不满足直接 return，减少嵌套层级
6. **Guard Clauses**：公共方法入口处集中验证参数，使用 `ArgumentNullException`
7. **Unity 对象生命周期**：销毁后的对象用 `if (obj != null)` 检查（不用 `?.`）

## ❌ 常见陷阱

1. **对 Unity Object 使用 `?.`** → 正确做法：使用 `if (obj != null) obj.Method()`
2. **假设 Inspector 赋值一定有值** → 正确做法：运行时仍需 null 检查或 `[Required]` 属性
3. **字典直接用索引器取值** → 正确做法：使用 `TryGetValue` 避免 `KeyNotFoundException`
4. **忽略 `GetComponentInChildren` 可能返回 null** → 正确做法：检查返回值
5. **在 null 检查和使用之间有延迟（异步/协程）** → 正确做法：使用前再次检查
6. **捕获异常后不处理** → 正确做法：至少 `Debug.LogError` + 合理的降级策略

## 📋 检查清单

- [ ] 所有 GetComponent/Find 调用后是否有 null 检查
- [ ] 所有 [SerializeField] 字段使用前是否验证了非 null
- [ ] 是否避免了对 Unity Object 使用 `?.` 运算符
- [ ] 字典操作是否使用了 `TryGetValue`
- [ ] 公共方法入口是否有参数验证（Guard Clauses）
- [ ] 事件触发是否安全（`?.Invoke()` 或 null 检查）
- [ ] 异步/协程中是否在 yield 后重新检查了引用有效性

## 🔗 关联技能

- [MonoBehaviour 生命周期最佳实践](../unity/monobehaviour-patterns.md)
- [Unity 中的异步编程](./async-await-unity.md)
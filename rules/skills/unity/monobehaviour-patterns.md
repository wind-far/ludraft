---
# 注意不要修改本文头文件，如修改，CodeBuddy（内网版）将按照默认逻辑设置
type: manual
---
# 技能：MonoBehaviour 生命周期最佳实践

> **领域**: unity
> **适用Agent**: 程序 / 主程
> **加载时机**: 需要编写或设计 MonoBehaviour 类时按需加载
> **大小**: ~1.5KB

## 📌 核心知识

1. **生命周期执行顺序**：Awake → OnEnable → Start → FixedUpdate → Update → LateUpdate → OnDisable → OnDestroy
2. **Awake vs Start**：Awake 用于自身初始化（不依赖其他对象），Start 用于依赖其他对象的初始化
3. **OnEnable/OnDisable 成对**：事件订阅在 OnEnable 中，取消订阅在 OnDisable 或 OnDestroy 中
4. **FixedUpdate vs Update**：物理相关逻辑放 FixedUpdate（固定时间步长），输入和渲染相关放 Update
5. **LateUpdate**：摄像机跟随、UI跟随等需要在 Update 后执行的逻辑
6. **Coroutine 生命周期**：协程随 GameObject 的 active 状态停止，OnDisable 时自动中断
7. **DontDestroyOnLoad**：跨场景的 Manager 类使用，但需防止重复创建（单例检查）
8. **OnApplicationPause / OnApplicationFocus**：移动平台切后台/回前台时的状态保存

## ✅ 最佳实践

1. **初始化分层**：Awake 缓存自身组件引用，Start 缓存外部引用和执行依赖逻辑
2. **避免在 Update 中使用 GetComponent/Find 系列**：在 Awake/Start 中缓存引用
3. **事件订阅/取消必须成对**：OnEnable 订阅 → OnDisable/OnDestroy 取消，避免内存泄漏
4. **空安全**：所有 GetComponent 返回值必须检查 null（使用 TryGetComponent 更佳）
5. **使用 [SerializeField] 替代 public 字段**：保持封装性的同时支持 Inspector 赋值
6. **协程替代方案**：简单延迟用 Invoke，复杂异步考虑 UniTask 或 async/await
7. **OnDestroy 清理**：释放所有订阅、取消协程、清理引用

## ❌ 常见陷阱

1. **Awake 中访问其他对象** → 正确做法：移到 Start 中，或使用 Script Execution Order
2. **Update 中频繁 new 对象** → 正确做法：对象池或提前分配缓存
3. **忘记在 OnDestroy 中取消事件订阅** → 正确做法：每个 += 必须有对应的 -=
4. **协程中不检查对象是否已销毁** → 正确做法：yield 后检查 `this != null` 或 `gameObject != null`
5. **在 OnDestroy 中访问已销毁的对象** → 正确做法：先检查 null 再访问
6. **多个 Awake 之间假设执行顺序** → 正确做法：使用 Script Execution Order 或事件驱动

## 📋 检查清单

- [ ] GetComponent/Find 调用是否都在 Awake/Start 中（非 Update）
- [ ] 所有事件订阅是否有对应的取消订阅
- [ ] OnDestroy 中是否清理了所有资源和引用
- [ ] 协程是否有超时保护或取消机制
- [ ] [SerializeField] 字段是否有 [Tooltip] 说明
- [ ] 是否避免了在 Update 中分配堆内存

## 🔗 关联技能

- [空安全最佳实践](../csharp/null-safety.md)
- [事件系统设计模式](../architecture/event-system.md)
- [Unity 性能优化模式](./performance-patterns.md)
---
# 注意不要修改本文头文件，如修改，CodeBuddy（内网版）将按照默认逻辑设置
type: manual
---
# 技能：Unity Test Framework 使用

> **领域**: testing
> **适用Agent**: QA / 程序
> **加载时机**: 需要编写或执行自动化测试时按需加载
> **大小**: ~1.5KB

## 📌 核心知识

1. **两种测试模式**：EditMode（不需要运行场景，速度快）和 PlayMode（需要运行场景，可测试 MonoBehaviour 生命周期）
2. **NUnit 框架**：Unity Test Framework 基于 NUnit 3.x，使用 `[Test]`、`[UnityTest]`、`[SetUp]`、`[TearDown]` 等特性
3. **`[Test]` vs `[UnityTest]`**：`[Test]` 普通同步测试；`[UnityTest]` 返回 `IEnumerator`，可 `yield return` 等待帧或时间
4. **Assembly Definition**：测试代码需放在带 `testAssemblies` 引用的 `.asmdef` 中
5. **测试文件位置**：EditMode → `Assets/Tests/EditMode/`，PlayMode → `Assets/Tests/PlayMode/`
6. **Assert 类**：`Assert.AreEqual`、`Assert.IsTrue`、`Assert.IsNotNull`、`Assert.Throws<T>` 等
7. **测试执行顺序**：SetUp → Test → TearDown（每个测试方法都会执行 SetUp/TearDown）

## ✅ 最佳实践

1. **AAA 模式**：Arrange（准备）→ Act（执行）→ Assert（断言），每个测试方法结构清晰
2. **命名规范**：`[测试对象]_[测试条件]_[期望结果]`，如 `Inventory_AddItem_IncrementsCount`
3. **AC 关联命名**：验收标准测试方法用 `AC001_` 前缀，如 `AC001_PlayerCanMoveForward()`
4. **Category 分类**：使用 `[Category("验收标准")]`、`[Category("边界测试")]` 等标签分组
5. **每个测试独立**：不依赖其他测试的执行结果或顺序，SetUp 中完整初始化
6. **Assert 消息**：每个 Assert 附带清晰消息，如 `Assert.AreEqual(5, count, "添加5个物品后背包数量应为5")`
7. **Mock 依赖**：纯逻辑类使用接口隔离 + Mock 实现，减少 PlayMode 测试的使用

## ❌ 常见陷阱

1. **测试之间共享状态** → 正确做法：每个测试 SetUp 中重新创建，TearDown 中清理
2. **PlayMode 测试不清理 GameObject** → 正确做法：TearDown 中 `Object.DestroyImmediate(go)`
3. **Assert 不写消息** → 正确做法：每个 Assert 都附带描述性消息
4. **测试中使用 Thread.Sleep** → 正确做法：使用 `yield return new WaitForSeconds()` 或帧等待
5. **测试硬编码绝对路径** → 正确做法：使用 `Application.dataPath` 或 TestFixture 数据
6. **只测正常流程** → 正确做法：每个功能必须包含正常/边界/异常三类测试
7. **测试中依赖网络/文件IO** → 正确做法：Mock 外部依赖

## 📋 检查清单

- [ ] 每条验收标准是否都有对应的测试方法（AC001_、AC002_...）
- [ ] 是否包含边界条件测试（空集合、最大/最小值、null 输入）
- [ ] 是否包含异常情况测试（无效参数、状态不正确时的调用）
- [ ] 测试之间是否相互独立（无共享状态）
- [ ] SetUp/TearDown 是否正确初始化和清理
- [ ] 所有 Assert 是否附带清晰的失败消息
- [ ] PlayMode 测试是否在 TearDown 中销毁了创建的 GameObject

## 🔗 关联技能

- [MonoBehaviour 生命周期最佳实践](../unity/monobehaviour-patterns.md)
- [空安全最佳实践](../csharp/null-safety.md)
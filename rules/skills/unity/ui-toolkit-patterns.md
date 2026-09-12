---
# 注意不要修改本文头文件，如修改，CodeBuddy（内网版）将按照默认逻辑设置
type: manual
---
# 技能：UGUI / UI Toolkit 模式

> **领域**: unity
> **适用Agent**: 程序 / UX / 主程
> **加载时机**: 需要开发或设计 UI 功能时按需加载
> **大小**: ~1.5KB

## 📌 核心知识

1. **Canvas 渲染模式**：Screen Space - Overlay（最常用）、Screen Space - Camera、World Space
2. **Canvas 分离**：将高频更新 UI 和静态 UI 放不同 Canvas，避免整体重建
3. **RectTransform**：Anchor（锚点）决定适配策略，Pivot（轴心点）决定旋转/缩放中心
4. **事件系统**：EventSystem → GraphicRaycaster → UI 元素（实现 IPointerClickHandler 等）
5. **布局系统**：HorizontalLayoutGroup / VerticalLayoutGroup / GridLayoutGroup + ContentSizeFitter
6. **ScrollView 优化**：大量列表项使用对象池复用（虚拟列表），避免一次性创建
7. **TextMeshPro**：优先使用 TMP 替代 Text 组件，渲染质量和性能更优

## ✅ 最佳实践

1. **MVC/MVP 分层**：View（MonoBehaviour UI组件引用） → Presenter（逻辑） → Model（数据），UI 不直接操作数据
2. **事件驱动更新**：UI 监听数据变化事件刷新，而非 Update 中轮询检查
3. **按钮回调注册**：代码中使用 `button.onClick.AddListener()`，OnDestroy 中 `RemoveAllListeners()`
4. **引用管理**：使用 `[SerializeField]` 绑定 UI 组件引用，不在运行时 Find
5. **UI 面板管理**：使用 UIManager 统一管理面板的打开/关闭/层级
6. **动画**：简单动画用 DOTween/Tween，复杂状态切换用 Animator
7. **适配策略**：CanvasScaler 使用 Scale With Screen Size，设计参考分辨率

## ❌ 常见陷阱

1. **所有 UI 在同一个 Canvas** → 正确做法：按更新频率和功能拆分 Canvas
2. **Update 中更新 UI 文本** → 正确做法：数据变化时通过事件通知 UI 更新
3. **ScrollView 中创建大量 Item** → 正确做法：使用对象池 + 虚拟列表
4. **未移除按钮事件监听** → 正确做法：OnDestroy 中 `RemoveAllListeners()`
5. **Raycast Target 默认勾选** → 正确做法：纯装饰性 Image/Text 关闭 Raycast Target
6. **大量 UI 元素使用 LayoutGroup** → 正确做法：静态布局直接手动设置 RectTransform

## 📋 检查清单

- [ ] Canvas 是否按功能/更新频率合理拆分
- [ ] UI 是否采用 MVC/MVP 分层（View 不含业务逻辑）
- [ ] 所有按钮监听是否在 OnDestroy 中移除
- [ ] ScrollView 是否使用了对象池（列表项 > 20 时）
- [ ] 纯装饰性 UI 元素是否关闭了 Raycast Target
- [ ] UI 引用是否通过 [SerializeField] 绑定（非运行时 Find）
- [ ] 是否使用 SceneSetupTool 同步场景创建代码

## 🔗 关联技能

- [MonoBehaviour 生命周期最佳实践](./monobehaviour-patterns.md)
- [事件系统设计模式](../architecture/event-system.md)
- [Unity 性能优化模式](./performance-patterns.md)
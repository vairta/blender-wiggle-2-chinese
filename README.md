<!--
Keep this document short & concise,
linking to external resources instead of including content in-line.
See 'release/text/readme.html' for the end user read-me.
-->

# Wiggle 2

这是 Wiggle 2 的人工翻译中文版本，对源代码没有做任何修改。

原作者：[https://github.com/shteeve3d/blender-wiggle](https://github.com/shteeve3d/blender-wiggle-2)

Wiggle 2是对[wiggle bones](https://github.com/shteeve3d/blender-wiggle)的彻底重写，是一个Blender插件。

## 特性

### 新的物理解算
- Wiggle 2的惯性摆动现在表现得更加逼真，尤其是在模拟简单的绳索或链条时。

### 支持挂钩
- 在Wiggle的骨骼上使用阻尼轨道约束将其固定到目标，其他骨骼也会做出相应物理反应。
!["Pinning"](/images/pinning.png?raw=true "Pinning")

### 支持碰撞
- Wiggle骨骼可以与指定的网格或集合碰撞，并以摩擦、弹跳甚至粘性反应。
!["Collision"](/images/collision.png?raw=true "Collision")

### 资产库链接及覆盖修改
- Wiggle 2支持blender资产库，允许修改并覆盖所有场景中的Wiggle效果。

### 改进的烘焙
- 一键烘焙将启用的Wiggle骨骼转换为关键帧。预解算帧选项让模拟帧数预先确定。或者将它与“循环模拟”一起使用，在时间线循环时继续无缝物理模拟。

### 新的UI
- 所有设置都可以从3D视图中的单个动画面板内进行编辑，更加便捷的工作流。

## 使用方法
- 安装并启用插件。
- 在场景中启用Wiggle 2。选中骨骼时，在3D视图的动画选项卡面板中。

!["Enable Scene"](/images/enable_scene.png?raw=true "Enable Scene")
- 选择骨架对象。

!["Select Armature"](/images/select_armature.png?raw=true "Select Armature")
- 在骨架上启用Wiggle。

!["Enable Armature"](/images/enable_armature.png?raw=true "Enable Armature")
- 在姿态模式下选择骨骼。

!["Select Pose Bone"](/images/select_pose_bone.png?raw=true "Select Pose Bone")
- 在骨骼的头部或尾部启用Wiggle。注意：如果骨骼连接到它的父级，头部将不可用（在这种情况下，只需要启用父级的尾部）。

!["Enable Bone"](/images/enable_bone.png?raw=true "Enable Bone")
- 在头部和尾部的下拉菜单中设置骨骼的物理特性数值。

!["Configure Bone"](/images/configure_bone.png?raw=true "Configure Bone")
- 选择一个碰撞对象或集合，使头部或尾部与其发生碰撞反应。同时，碰撞行为提供更多的选项以调整物理效果。

!["Configure Collision"](/images/configure_collision.png?raw=true "Configure Collision")
- “全局设置”提供了一些方便的功能，例如“重置模拟”，“全选Wiggle”选择所有启用的Wiggle骨骼，以及“复制到选择”将活动骨骼的Wiggle设置复制到选中骨骼。请注意，始终可以一次调整多个选定骨骼的个别设置。“循环模拟”将阻止物理模拟在时间线结束并重新开始循环时的重置。“质量”指的是物理模拟解算的迭代次数，这对绳索模拟效果作用显著。

!["Utilities"](/images/utilities.png?raw=true "Utilities")
- 烘培Wiggle会将实时物理模拟转换为关键帧。它将对视图中所有启用的Wiggle的骨骼进行烘培。覆盖合并当前骨架动画中的关键帧，而不会创建新的关键帧。“预解算帧”指定模拟的帧数，使需要模拟的帧数预先确定，它还可以与“循环模拟”一起使用，让模拟在时间线循环时继续。

!["Bake"](/images/bake.png?raw=true "Bake")

许可证
-------

Wiggle 2 整体作为 GNU 3 通用公共许可证许可。
单个文件可能具有不同但兼容的许可证。

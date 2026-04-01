# 演示模块概况

## 入口函数检索范围

- 头文件: src/ControlSystem.h
- 源文件: src/ControlSystem.cpp

## 模块说明

温控系统模块，包含 PID 控制、PTC 加热器管理、风扇控制等功能。
用于演示 clangd-call-tree-skill 的端到端流程。

## 关键接口

- `ControlSystem::init` — 初始化控制系统
- `ControlSystem::runControlCycle` — 控制循环主入口
- `ControlSystem::setTargetTemp` — 设置目标温度
- `ControlSystem::setMode` — 设置运行模式

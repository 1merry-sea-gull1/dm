# DM 轮腿机器人项目说明

本仓库保存 DM-MC02 控制板、USB2CAN 调试工具以及轮腿机器人整机的软硬件资料。

当前机器人使用：

- 控制板：`DM-MC02`
- 电机：6 个 `DM-J4310-2EC V1.2`
- 4 个关节电机
- 2 个轮毂用途电机，型号与关节电机相同，但控制功能不同
- 2 路 CAN，每路 3 个电机
- 供电：24 V 电源连接分电板，分电板为电机和控制板供电

```text
24 V 电源
   │
分电板
   ├─ 电机电源
   └─ DM-MC02 控制板
          │
      CAN1 / CAN2
          │
       CAN 分线板
       ├─ CAN1：3 个电机
       └─ CAN2：3 个电机
```

## 仓库结构

```text
dm/
├─ dm-mc02-master/       控制板说明书、图纸、3D 模型和例程
├─ dm_tools_master/      USB 转 CAN 工具、固件和 SDK
├─ wheel-legged-master/  轮腿机器人结构、固件和仿真
├─ .gitattributes        大型文件的 Git LFS 规则
└─ .gitignore            Git 忽略规则
```

## 顶层目录

### `dm-mc02-master`

DM-MC02 控制板的硬件和开发资料。

| 目录 | 内容 |
|---|---|
| `说明书/` | 控制板说明书和芯片数据手册 |
| `2D图纸/` | 原理图、封装参考和 LCD 模块资料 |
| `3D模型/` | 控制板、外壳和 LCD 模块的 STEP/SolidWorks 模型 |
| `图片/` | 控制板照片和参数图 |
| `例程/` | 18 个 STM32H7 外设例程，包括 CAN、FDCAN、IMU、ADC、TIM、UART 等 |

该目录主要用于查询硬件引脚、原理图和官方例程，不参与轮腿主固件编译。

### `dm_tools_master`

USB 转 CAN/CANFD 工具资料，实际内容位于 `dm-tools-master/` 子目录。

| 目录 | 内容 |
|---|---|
| `USB2CANFD/` | 单路 USB 转 CANFD 的 SDK、固件、外壳模型和说明书 |
| `USB2CANFD_Dual/` | 双路 USB 转 CANFD 资料 |
| `USB2CANFD通用升级工具/` | 工具固件升级程序 |
| `gs_usb_drives/` | Linux `gs_usb` 驱动资料 |
| `DM-LinkX-4C/`、`DM_DeviceSDK/`、`电机调试工具/` | 第三方 SDK 或调试工具入口；当前快照中部分目录为空 |

该目录用于上位机调试、CAN 通信测试和电机调试，不参与轮腿固件编译。

### `wheel-legged-master`

轮腿机器人整机资料，是当前主要开发目录。

```text
wheel-legged-master/
├─ README.md
├─ README.zh.md
├─ README.en.md
├─ LICENSE
└─ 硬件/
   ├─ 打印件版/
   └─ 机加版/
```

打印件版和机加版主要包含：

| 目录或文件 | 内容 |
|---|---|
| `代码/` | STM32H723 轮腿控制固件 |
| `结构件/` 或 `结构及安装/` | 3D 打印件或机加件的结构模型和安装资料 |
| `硬件接线图/` | 控制板、分电板、电机和电源接线参考 |
| `购买清单/` | BOM、电机和结构件采购清单 |
| `轮子安装/` | 轮毂安装视频和爆炸图 |
| `轮足分电板geber.zip` | 分电板 PCB 制造文件 |
| `仿真/` | 打印件版包含的轮腿仿真资料 |

## 固件版本

轮腿仓库中包含四套结构相似、参数不同的固件，不能混用。

| 版本 | 路径 | 用途 |
|---|---|---|
| 打印件版官方主版 | `硬件/打印件版/代码/DM-balance打印件版本/DM-balanceV1` | 当前开发工程 |
| 打印件版群友改版 | `硬件/打印件版/代码/DM-balance打印件版本（群友）/DM-balance打印件版本群友` | 增加 Roll 补偿、跳跃和期望速度处理 |
| 机加版官方 | `硬件/机加版/代码/DM-balance机加工版本` | 机加结构配套固件 |
| 机加版群友 SBUS | `硬件/机加版/代码/群友机加工sbus版本/DM_Balance_Hy_V1_0/DM_Balance_Hy_V1_0` | 使用 SBUS 遥控器的改版 |

注意：

- 打印件版和机加版的 IMU 安装姿态、结构参数和控制参数不同，不能互相烧录。
- 当前六电机适配只修改打印件版官方主版。
- 群友版和机加版仍保留各自原始内容。

## 当前固件工程

当前工程：

```text
wheel-legged-master/硬件/打印件版/代码/
DM-balance打印件版本/DM-balanceV1/
```

工程目录：

```text
DM-balanceV1/
├─ CtrlBoard-H7_IMU.ioc   CubeMX 外设配置
├─ Core/                  STM32 初始化和 FreeRTOS 启动
├─ User/                  自写业务代码
│  ├─ APP/                机器人控制任务
│  ├─ Bsp/                板级驱动
│  ├─ Devices/            IMU、电机等器件驱动
│  ├─ Algorithm/          EKF、PID、VMC 等算法
│  ├─ Controller/         通用控制算法
│  └─ Lib/                数学工具函数
├─ Drivers/               ST HAL 和 CMSIS
├─ Middlewares/           FreeRTOS
└─ MDK-ARM/               Keil 工程和编译输出
```

### `Core/`

CubeMX 生成的板级初始化和任务入口。

| 文件 | 功能 |
|---|---|
| `main.c` | 时钟、GPIO、DWT、IMU、电源、CAN 和 FreeRTOS 初始化 |
| `freertos.c` | 创建姿态、左右腿、观测器和 PS2 任务，配置任务优先级 |
| `fdcan.c` | CAN1、CAN2 的 FDCAN 配置 |
| `spi.c` | BMI088 等 SPI 外设配置 |
| `tim.c` | 定时器和 PWM 时基配置 |
| `gpio.c` | GPIO 初始化 |
| `dma.c` | DMA 初始化 |
| `stm32h7xx_it.c` | STM32 中断入口 |

一般通过 `CtrlBoard-H7_IMU.ioc` 修改外设配置，不直接手改生成代码。

### `User/APP/`

轮腿机器人的主要业务代码。

| 文件 | 功能 |
|---|---|
| `chassisR_task.c/.h` | 右腿任务，控制右侧 2 个关节电机和右轮毂电机 |
| `chassisL_task.c/.h` | 左腿任务，控制左侧 2 个关节电机和左轮毂电机 |
| `INS_task.c/.h` | 读取 BMI088 并进行姿态解算 |
| `observe_task.c/.h` | 速度估计、离地检测和观测器 |
| `ps2_task.c/.h` | PS2 手柄输入 |

控制流程：

```text
BMI088
  │
姿态解算
  │
VMC / LQR / PID
  │
关节扭矩 + 轮毂扭矩
  │
CAN1 / CAN2
```

### `User/Bsp/`

| 文件 | 功能 |
|---|---|
| `can_bsp.c/.h` | FDCAN 发送、接收中断和反馈 ID 分发 |
| `bsp_dwt.c/.h` | DWT 微秒级计时和延时 |
| `bsp_PWM.c/.h` | PWM、蜂鸣器或 LED 等板级输出 |

`can_bsp.c` 中的反馈分发是排查 CAN 通信问题的重点。

### `User/Devices/`

| 目录或文件 | 功能 |
|---|---|
| `DM_Motor/dm4310_drv.c/.h` | DM4310 使能、MIT 控制帧发送和反馈解码 |
| `BMI088/BMI088driver.c` | IMU 数据读取和温控 |
| `BMI088/BMI088Middleware.c` | BMI088 的 SPI 底层读写 |
| `BMI088/BMI088reg.h` | BMI088 寄存器定义 |

### `User/Algorithm/`

| 文件 | 功能 |
|---|---|
| `EKF/QuaternionEKF.c` | 四元数姿态融合 |
| `kalman/kalman_filter.c` | 卡尔曼滤波 |
| `mahony/mahony_filter.c` | Mahony 姿态解算 |
| `PID/pid.c` | PID 控制器 |
| `VMC/VMC_calc.c` | 虚拟模型控制，将腿长和摆角转换为关节目标 |

### `User/Controller/` 和 `User/Lib/`

- `User/Controller/controller.c/.h`：LQR、模糊 PID、ADRC 等通用控制算法。
- `User/Lib/user_lib.c/.h`：限幅、角度归一化、斜坡等数学工具。

### `MDK-ARM/`

| 文件或目录 | 功能 |
|---|---|
| `CtrlBoard-H7_IMU.uvprojx` | Keil 编译入口 |
| `CtrlBoard-H7_IMU.uvoptx` | Keil 工程选项 |
| `startup_stm32h723xx.s` | STM32H723 启动文件 |
| `RTE/`、`DebugConfig/` | Keil 运行环境和调试配置 |
| `CtrlBoard-H7_IMU/` | 编译输出目录，包含 `.axf`、`.hex`、`.o`、`.map` 等 |

`MDK-ARM/CtrlBoard-H7_IMU/` 属于生成物，不进入 Git 版本历史。

### `Drivers/` 和 `Middlewares/`

- `Drivers/`：ST 官方 STM32H7 HAL 和 CMSIS。
- `Middlewares/`：FreeRTOS 内核。

这两部分属于第三方依赖，通常不直接修改。

## 电机和 CAN 配置

当前固件配置如下，六台电机的控制 ID 和反馈 ID 均唯一。

| CAN | 电机 | 控制 ID | 反馈 ID |
|---|---|---:|---:|
| CAN1 | 1号电机，右侧关节 0 | `0x01` | `0x11` |
| CAN1 | 2号电机，右侧轮毂 | `0x02` | `0x12` |
| CAN1 | 3号电机，右侧关节 1 | `0x03` | `0x13` |
| CAN2 | 4号电机，左侧关节 0 | `0x04` | `0x14` |
| CAN2 | 5号电机，左侧轮毂 | `0x05` | `0x15` |
| CAN2 | 6号电机，左侧关节 1 | `0x06` | `0x16` |

1、3、4、6 号电机用于关节，2、5 号电机用于轮毂，但六台电机型号均为 DM-J4310-2EC V1.2。

这些配置必须与电机内部参数一致：

- 电机控制 ID
- 电机反馈 ID
- MIT 模式
- 两路 CAN 均为 1 Mbps
- 电机方向和零位

## 版本记录

### `v0.2` 实际电机 ID 配置

将六台电机的控制 ID 和反馈 ID 更新为实际配置：

- CAN1：1 号关节 `0x01/0x11`、2 号轮毂 `0x02/0x12`、3 号关节 `0x03/0x13`
- CAN2：4 号关节 `0x04/0x14`、5 号轮毂 `0x05/0x15`、6 号关节 `0x06/0x16`
- 1、3、4、6 号为关节电机，2、5 号为轮毂电机
- 轮毂与关节使用相同型号 DM4310，仅控制功能和安装位置不同
- 保留 `v0.1` 的统一 DM4310 协议和轮毂控制逻辑

修改文件：

```text
User/APP/chassisR_task.c
User/APP/chassisL_task.c
User/Bsp/can_bsp.c
README.md
```

编译结果：

- 0 Error(s)
- 0 Warning(s)
- `Code=52828`，`RO-data=3196`，`RW-data=804`，`ZI-data=36604`

固件输出路径与 `v0.1` 相同。`v0.2` 已完成编译验证，尚未完成实机测试。

### `v0.1` 六电机 DM4310 适配

`v0.1` 将原来的“4 个 DM4310 关节电机 + 2 个轮毂电机”适配为 6 个同型号 DM4310。

已完成：

- 4 个关节和 2 个轮毂统一使用 DM4310 MIT 协议量程
- 轮毂发送从 `mit_ctrl2()` 改为 `mit_ctrl()`
- 轮毂反馈改为 `dm4310_wheel_fbdata()`
- 删除旧轮毂型号专用参量和重复 MIT 发送函数
- 保留原 CAN1/CAN2 分配、电机 ID 和轮毂控制功能

修改文件：

```text
User/Devices/DM_Motor/dm4310_drv.c
User/Devices/DM_Motor/dm4310_drv.h
User/Bsp/can_bsp.c
User/APP/chassisR_task.c
User/APP/chassisL_task.c
```

编译结果：

- Keil ARMCC 5.06 update 5
- 0 Error(s)
- 0 Warning(s)
- `Code=52820`，`RO-data=3196`，`RW-data=804`，`ZI-data=36604`

固件输出：

```text
MDK-ARM/CtrlBoard-H7_IMU/CtrlBoard-H7_IMU.hex
MDK-ARM/CtrlBoard-H7_IMU/CtrlBoard-H7_IMU.axf
```

`v0.1` 已完成代码适配和编译验证，但尚未完成实机测试。首次测试前应架空轮子，先确认电机 ID、反馈、转向、扭矩方向和紧急断电措施。

## Git 版本管理

当前分支和标签：

| 名称 | 用途 |
|---|---|
| `main` | 未修改的原始版本 |
| `baseline-original` | 原始基线标签 |
| `adapt/six-dm4310` | 六电机适配开发分支 |
| `v0.1` | 六个 DM4310 适配版本 |
| `v0.2` | 六电机实际 CAN ID 配置版本 |

大型视频、CAD 模型、压缩包和可执行文件使用 Git LFS 管理。首次克隆后需要执行：

```powershell
git lfs install
git lfs pull
```

编译产物、Simulink 缓存、SolidWorks 临时文件等已通过 `.gitignore` 排除。

查看历史版本：

```powershell
git log --oneline --graph --decorate --all
git show v0.2
git diff v0.1..v0.2
```

## 修改边界

通常需要修改：

```text
User/APP/
User/Devices/DM_Motor/
User/Bsp/can_bsp.c
```

通常不直接修改：

```text
Core/                  优先通过 .ioc 重新生成
Drivers/               ST 官方库
Middlewares/           FreeRTOS
MDK-ARM/CtrlBoard-H7_IMU/  编译生成物
```

修改控制参数或电机协议后，应重新编译并保存一个新的 Git 提交。经过实机验证的版本应单独打标签，例如 `v0.2`。

硬件自动发现结果 
组件	发现结果	状态
LCD 驱动 IC	ST7701 (MIPI-DSI, v1.1.3 driver)	✅ 已确认
触摸控制器	GT911 (ID: "911", Config v250)	✅ 已确认
摄像头	OV02C10 (MIPI-CSI, 1288×728)	✅ 已确认
音频	ES8311 Codec (I2S, 44.1kHz/16bit)	✅ 已确认
Wi-Fi	ESP32-C6 via SDIO 4-bit 40MHz	✅ 已确认
PSRAM	32MB AP Gen4 @ 200MHz	✅ 已确认
Flash	16MB Boya QIO 80MHz	✅ 已确认
背光 GPIO	GPIO23 (LEDC PWM)	✅ 已确认
C6 Reset GPIO	GPIO54	✅ 已确认
SDIO GPIOs	CLK:18, CMD:19, D0-D3:14-17	✅ 已确认
运行框架	ESP_Brookesia v0.4.1 Phone	✅ 已确认
ESP-IDF 版本	v5.5	✅ 已确认
芯片版本	ESP32-P4 v1.3 (eco2)	✅ 已确认



Demo 已经在 480×800 上成功运行 ESP_Brookesia Phone — 证明这个分辨率完全兼容
使用的 BSP 标识为 ESP32_P4_EV，与官方板相同 — 可以直接复用
ST7701 和 GT911 都有现成的 ESP Component Registry 组件
Wi-Fi SDIO 通道已验证可用（成功连上了你的路由器获得 IP 192.168.178.95）


CMakeLists.txt              ← 项目根构建文件
sdkconfig.defaults          ← ESP32-P4 PSRAM/Wi-Fi 配置
partitions.csv              ← 3MB app 分区
main/
  idf_component.yml         ← 依赖: BSP + esp_brookesia ~0.4.1
  main.cpp                  ← BSP初始化 → Brookesia Phone → 安装SolarApp
  solar_app.cpp/.h          ← PhoneApp子类: run()/back() + 1s刷新定时器
  api/
    data_model.h            ← C结构体: Dashboard/Strategy/Config/History
    solar_api.cpp/.h        ← HTTP客户端包装所有后端接口
  storage/
    nvs_config.cpp/.h       ← NVS读写: WiFi/Server/APIKey配置
  tasks/
    data_task.cpp/.h        ← FreeRTOS任务: WiFi连接 + 5s/60s轮询
  screens/
    setup_wizard.c/.h       ← 首次启动配置向导(5个输入字段+键盘)
    overview.c/.h           ← 概览: 3个弧形仪表 + 电力流向图
    control.c/.h            ← 控制: 滑块设置负载 + Auto开关 + 策略选择
    energy.c/.h             ← 能源: 6格kWh瓷砖 + 今日/昨日柱状图
    history.c/.h            ← 历史: 1h/6h/24h 电网功率折线图
    config_screen.c/.h      ← 配置: 策略参数列表 + 弹窗编辑
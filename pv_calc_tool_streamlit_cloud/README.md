# 光伏项目自动测算工具

这是一个内部使用的工商业分布式光伏项目初步测算 MVP，采用 Python + Streamlit 实现。第一版重点是可运行、公式透明、参数可修改、结果可导出 Excel。

## 功能

- 容量测算：支持屋顶总面积、可利用面积、已确认可铺设面积三种口径，避免重复扣减。
- 地图面积：支持上传地图截图后点选闭合多边形，并按可调整比例尺换算面积。
- 消纳测算：支持 15 分钟负荷曲线、月度尖峰平谷电量、快速估算，并引入节假日/停产日历。
- 造价测算：按分项元/Wp 造价、容量规模系数和不可预见费计算总投资。
- 收益测算：生成运营期现金流，计算静态回收期、动态回收期、IRR、NPV、LCOE。
- 动态调整：按消纳比例、回收期、IRR、单位投资、装机密度等规则输出风险提示。
- 敏感性分析：对总投资、发电小时数、自发自用比例、自用电价、上网电价做 -10% 到 +10% 扰动。
- Excel 导出：生成完整测算工作簿。

## 项目结构

```text
pv_calc_tool/
  app.py
  requirements.txt
  README.md
  config/
    __init__.py
    default_params.py
  modules/
    __init__.py
    capacity_calc.py
    image_area_estimator.py
    bill_parser.py
    consumption_calc.py
    cost_calc.py
    revenue_calc.py
    finance_calc.py
    sensitivity_calc.py
    export_excel.py
  templates/
    excel_template.xlsx
  sample_data/
    sample_bill.xlsx
    sample_roof_image.png
```

## 安装与运行

```bash
cd pv_calc_tool
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

如果使用 Codex 桌面自带运行时，可以直接在项目目录执行：

```bash
C:\Users\jyb99\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m streamlit run app.py
```

## 主要公式

屋顶总面积口径：有效安装面积 = 输入面积 × 屋顶利用率 × (1 - 综合扣减比例) × (1 - 排布损耗)

可利用面积口径：有效安装面积 = 输入面积 × (1 - 综合扣减比例) × (1 - 排布损耗)

已确认可铺设面积口径：有效安装面积 = 输入面积 × (1 - 排布损耗)

可安装组件数 = floor(有效安装面积 / 单块组件面积)

直流侧装机容量(kWp) = 可安装组件数 × 单块组件功率(kWp)

年白天用电量 = 年用电量 × 白天用电比例

理论自用电量 = min(年光伏发电量, 年白天用电量)

自发自用比例 = min(理论自用电量 / 年光伏发电量, 生产制度自用比例上限)

基础单位造价 = 各分项单瓦造价之和

基础投资 = 装机容量(Wp) × 调整后单位造价(元/Wp)

总投资 = 基础投资 + 不可预见费 + 其他一次性费用

首年发电量 = 装机容量(kWp) × 等效利用小时数 × (1 - 首年衰减率)

第 n 年发电量 = 首年发电量 × (1 - 后续年衰减率)^(n-1)

年净现金流 = 年总收入 - 年运营成本 - 税费

当前收益测算函数为 `simplified_project_cashflow` 口径，返回 `finance_model_scope = simplified_unlevered_preliminary`。

NPV = 按折现率折现后的现金流净现值

IRR = 使 NPV = 0 的折现率

LCOE = 全生命周期折现成本 / 全生命周期折现发电量

## 第一版限制

- 地图比例尺像素长度必须根据当前截图重新测量；地图缩放或截图尺寸变化后不能沿用旧像素长度。
- OCR 预留了文本解析接口，PDF 扫描件仍需人工复核；第一版建议优先上传结构化 Excel 电费单或手动修正。
- 当前收益测算为简化全投资现金流测算口径，尚未完整考虑融资贷款、折旧抵税、增值税及附加、残值、逆变器更换、屋顶租金递增和合同能源管理分成。
- 当前区县光照数据为省级代表值或内置估算值，不是实测区县级辐照数据。正式测算请使用气象数据、PVsyst、Meteonorm、Solargis 或设计院资源报告复核。
- 分时电价时段已预留 `data/tou_period_config.csv`，正式测算请按当地最新分时电价政策配置尖峰平谷时段。
- 消纳模型正式投资决策前应补充逐时负荷曲线、组件排布图、并网方案和现场踏勘数据。

## 使用示例

1. 在 Step 1 输入可利用面积、组件面积、组件功率、屋顶利用率和扣减比例，得到装机容量。
2. 在 Step 2 上传 Excel 电费单或填写年用电量，选择生产制度，得到自发自用比例和余电上网比例。
3. 在 Step 3 调整各分项元/Wp 造价，得到总投资和单瓦造价。
4. 在 Step 4 输入等效利用小时数、电价、运营成本和折现率，查看现金流、IRR、NPV、LCOE。
5. 在 Step 5 查看风险提示和敏感性分析。
6. 在 Step 6 下载 Excel 测算报告。

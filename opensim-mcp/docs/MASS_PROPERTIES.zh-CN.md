# CAD 质量、质心与惯量交接

v1.4.1 新增一个只读工具 `convert_body_mass_properties`，不改输入文件、API/GUI 模型或网页。它把明确提供的 CAD 物理参数转换成 `assemble_wearable_model` 所需的三个 SI 字段，并返回来源与数值检查。不限于上肢、下肢或某种外骨骼。

## 最小用法

下面是原创解析示例，不能用于实际设备选型或证明人体收益：

```json
{
  "properties": {
    "mass": 2000,
    "mass_unit": "g",
    "center_of_mass": [10, 20, 30],
    "length_unit": "mm",
    "inertia": [20000, 25000, 30000, 1000, 2000, 3000],
    "inertia_unit": "kg_mm2",
    "inertia_reference": "center_of_mass",
    "inertia_convention": "tensor_entries",
    "source_frame": "CAD part frame",
    "source_description": "Original analytic demonstration, not measured hardware"
  },
  "frame_transform": {
    "target_frame": "device body frame",
    "rotation_source_to_target": [[0,-1,0],[1,0,0],[0,0,1]],
    "translation_source_origin_in_target_m": [0.1,0.2,0.3]
  }
}
```

返回 `body_parameters`：质量 2 kg、质心 `[0.08,0.21,0.33]` m、中心惯量 `[0.025,0.02,0.03,-0.001,-0.003,0.002]` kg·m²。把这三个字段填入已明确父体、网格和连接关节的 link；其余报告字段不填入 link。

## 必须明确的约定

| 字段 | 支持的含义 |
|---|---|
| mass_unit | `kg` 或 `g` |
| length_unit | 仅用于源质心的 `m`、`cm`、`mm` |
| inertia_unit | `kg_m2`、`kg_mm2`、`g_mm2`、`g_cm2`；不根据质量/长度单位猜测 |
| inertia | 6项 `[xx,yy,zz,xy,xz,yz]`，或9项行优先 `[xx,xy,xz,yx,yy,yz,zx,zy,zz]` |
| inertia_reference | `center_of_mass` 为质心处；`source_origin` 为源坐标原点处，先按质量与质心减去平行轴项 |
| inertia_convention | `tensor_entries` 为惯量矩阵的实际非对角项；`positive_products` 表示输入非对角项是积分 ∫xy dm、∫xz dm、∫yz dm，转换时取负号；“positive”不代表数值必须为正 |
| rotation_source_to_target | 3×3右手正交矩阵，满足 `p_target_m = R * p_source_m + t`；拒绝镜像、缩放和剪切，不自动修正 |
| translation_source_origin_in_target_m | 源原点在目标体框架中的位置，始终为米 |
| source_frame / target_frame | 两端框架的明确名称；同名要求恒等变换 |
| source_description | 参数来源说明，由调用者提供，工具不证明其真实性 |

输出惯量始终在**目标体轴下、关于质心**。改变目标框架原点只改变质心坐标，不给中心惯量再次添加平行轴项。

质心和惯量换到新体框架时，网格顶点、子关节中心及轴向也必须换到相同框架。**本工具不变换网格或关节，也不把该变换误当作装置在人体上的安装位姿。** 若网格与局部 CAD 框架保持不变，使用恒等数值变换，把身体安装位姿继续交给既有 link 参数。

## 校验与范围

拒绝非有限数、非对称惯量、非正定中心惯量及不满足主惯量三角不等式的输入；旋转前后主惯量须一致。容差为惯量尺度的 `1e-10`，不通过裁剪负特征值或换单位来“修好”输入。源原点离质心过远、平行轴减法损失过大时要求直接提供中心惯量。

有限实体剖面要求正定惯量；理想质点、理想线和数值退化剖面不在本功能支持范围。薄片三角裕量近零会提示，不等于已确认实际材料分布。

既有 `assemble_wearable_model` 对所有物理 link 在原生计算前执行相同惯量校验，并在原生保存重开后回读每件新增刚体的质量、质心和六项惯量。第二件非法不会导致第一件先写入。只显示模式行为保持。

这里不验证 CAD 材料/密度真实、外购件包络质量、网格和惯量是否匹配，也不估计绑带力、助力或代谢能耗。当前 SolidWorks 质量接口输出的9项惯量应结合实际 API、材料/覆盖标记和参考坐标核对，禁止仅凭字段名自动套用符号约定。

数学约定依据官方 [Simbody Inertia](https://simbody.github.io/3.7.0/classSimTK_1_1Inertia__.html) 与本机 OpenSim 4.6绑定的 `Inertia.getMoments/getProducts`；本地解析和原生回归结果单独记录。

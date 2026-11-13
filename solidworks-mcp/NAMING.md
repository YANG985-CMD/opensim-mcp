# CAD 组织与命名默认规则

适用：本 MCP 新建或整理的交付。项目已有正式编号时优先遵守原编号，不批量覆盖历史文件。

## 装配树与目录

- 大装配按功能建立约 3～8 个主要文件夹，并默认折叠。零件保持独立，不为缩短树而删除、隐藏、抑制或合并零件。
- 外骨骼主要分为：腰部固定结构、右髋与大腿支架、左髋与大腿支架、右侧气动模块、左侧气动模块。
- 一套机构优先交付一个可动总装；用配合尺寸表达姿态，避免为每个角度复制一份总装。
- 正式文件按 CAD/总装文件、CAD/Parts/零件文件、STL/导出、设计源文件/说明与映射分开。诊断、缓存、解包及中间导出只放指定 E 盘临时目录。

## 文件名称

本项目采用 `EXO-模块-序号_英文用途[_R或_L].扩展名`。这是项目约定，不是声称 ISO 或 SOLIDWORKS 强制要求该格式。

| 模块 | 用途 |
|---|---|
| ASM | 总装 |
| WST | 腰部结构 |
| HIP | 髋关节与电机接口 |
| THG | 大腿支架与腿托 |
| PAM | 气动肌肉、端部及滑座 |
| COM | 多处共用的同一文件 |

编号在项目中唯一，不把旧编号重复分配给另一个零件。用途简短、明确；实际不同的左右镜像件用 R/L 区分。同一原生文件的重复实例保留实例号，不为每个螺栓另造一个文件。未经几何/配置核对，不把“看起来一样”的镜像或标准件合并。

以 ASCII 字母、数字、连字符、下划线作为文件名字符，便于 STL、脚本和跨软件交换；文件夹及中文用途表可使用中文。版本 R01 等放在交付目录或属性/清单中，避免“最终版、最终2、修改后”等反复改名。Env 表示概念外形包络，不误称可直接制造的真实硬件模型。

STL 与来源零件使用相同名称主体，例如 `EXO-PAM-003_UpperSlideCarriage_R.SLDPRT` 对应同名 `.stl`；实际编号以项目命名映射为准。总装 STL 是整体几何导出，不代表适合整体打印。

需要分件或打印交付时，总装 STL 不能代替逐零件导出。按唯一原生零件导出一份，在清单记录装配数量；气动肌肉等明确仅作占位且无需打印的件排除，并列出排除项。定制结构件、外购件/硬件包络、柔性件分别归类；有 STL 不等于允许用塑料替代金属承载件。完成前核对清单覆盖率、单位、原生文件哈希和导出前后状态。中断必须标明已完成/未完成数量，不能用单份总装导出宣称分件交付完成。

## 变更与校验

已保存文件批量改名用 SOLIDWORKS 原生引用感知接口，不直接在文件系统改名。本机采用 SaveAs3 / IAdvancedSaveAsOptions / SaveAllAsCopy；Pack and Go 接口在返回对象前报错，不作为已验证能力。保留源版本，检查新包重开后所有引用、配合、固定状态、位姿和模块文件夹。整理前后 STL 比较有向三角面几何；重开导致局部重新划分时明确报告差异上界及事先指定的容差，不能直接称逐面相同。零件数减少必须另有明确设计理由。

## 官方依据

- [SOLIDWORKS PDM：用序列号自动命名文件](https://help.solidworks.com/2025/english/EnterprisePDM/Admin/t_serial_number_auto_naming_part.htm?id=2.22.3)：唯一编号的管理思路。
- [SOLIDWORKS：修改组件文件名](https://help.solidworks.com/2019/English/SolidWorks/sldworks/HIDD_RENAME_COMP.htm)：批量改名建议使用 Pack and Go，并说明闭合文档引用更新问题。
- [SOLIDWORKS：Pack and Go](https://help.solidworks.com/2023/english/SolidWorks/sldworks/r_pack_go_db.htm?id=cf776154a9b84ecc996ebe4512227489)：命名及相关引用统一打包。
- [NASA MSFC CAD 标准，第 25 页编号/命名表](https://standards.nasa.gov/sites/default/files/standards/MSFC/E/0/msfc-std-3528.pdf)：示例将文件标识与描述名称分别管理；本文仅参考该思路，不采用或宣称符合 NASA 编号体系。

默认要求已同步到 MCP 的初始化说明、guide 资源及 `sw_organize_assembly`、`sw_package_assembly` 工具。最终实机验证范围以 VERIFICATION.md 为准。

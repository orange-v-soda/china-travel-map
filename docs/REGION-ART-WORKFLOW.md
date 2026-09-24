# 区划艺术底图：唯一工作流

本文件是区划艺术底图的唯一流程说明。旧的 `1024/1536` 单区划画布、动态比例尺、模型可见行政边框、旧图二次编辑、整区一次性生成和带文字底图流程均已废止。

## 总原则

1. 页面中的 `balanced` 区划路径是唯一几何真相；真实地图只提供区划内部的地理语义。
2. 所有区划使用同一页面坐标系和同一比例尺。较大的区划增加生成窗口，不能缩小区划。
3. 语义先联合、图像后独立：公共边界先在联合 SVG 中协调，每个区划仍单独生成和发布。
4. 图像生成只负责把语义转换成画面；轮廓、编辑范围、锁定像素、合并和裁切均由确定性脚本负责。
5. 页面只加载最终 WebP。语义 SVG、mask、计划和提示词保留在仓库中，但不叠加到页面。

## 产物链

| 步骤 | 输入 | 产物 | 下一步如何使用 |
|---|---|---|---|
| 0. 区域研究 | 真实高程、河湖、县级聚落、地标资料 | 区域配置与分片提示词 | 约束语义 SVG 和生图内容 |
| 1. 锁定几何 | `JIANGXI_ART.cities[*].balanced` | canonical path、path bounds | 生成 mask、窗口计划和发布 bounds |
| 2. 联合语义 | 已验收联合 SVG、新区划语义初稿、共享边界 | 最新联合语义 SVG、联合状态 JSON | 所有目标窗口从此 SVG 裁取语义 |
| 3. 固定比例分片 | canonical path、固定比例配置 | `*-plan.json` | 决定窗口数量、顺序、重叠所有权 |
| 4. 构造生图输入 | 联合 SVG、已验收邻区底图、已验收前序窗口 | `*-context.png`、`*-mask.png` | 作为图像工具的图 1 与图 2 |
| 5. 独立生图 | context、mask、基础提示词、区域提示词 | 每个窗口的 raw 图 | 恢复所有不可编辑像素 |
| 6. 恢复与合并 | raw 图、context、二值 mask、plan | restored 窗口、canonical PNG | QA 和发布 |
| 7. QA | canonical PNG、联合语义、邻区成品 | 联合检查图、验收结论 | 通过后转 WebP |
| 8. 发布 | canonical PNG、workflow、tile manifest | 版本化 WebP、更新后的页面清单 | GitHub Pages 正式页面 |

## 0. 区域研究与提示词配置

先读取真实地理，再决定目标区划的山地、平原、水系、县级聚落和一个主要地标。研究结果不改变项目区划轮廓。

必须按窗口描述真实差异。九江西片是连续山地、森林、狭谷和稀疏县镇；东片是长江—鄱阳湖平原、集中城市带和庐山。二者不能复用同一段区域提示词。

- 可复用：`artwork/prompts/base.md` 中的画风、mask、水域、文字和锁定规则。
- 必须调整：区域地貌、县城分布、城市密度、农田类型、地标及各窗口差异。
- 禁止：不断追加修正句形成提示词堆叠。冲突时应改写区域提示或语义图。

## 1. 锁定项目几何与比例尺

轮廓只读取 `dist/jiangxi-art-data.js` 中的 balanced path。mask、联合 SVG、窗口计划、canonical 图和页面 clipPath 必须共享这条坐标链。

固定配置位于 `artwork/fixed-scale-generation.json`：

- 语义输入画布：`2048 × 2048 px`
- 每个窗口覆盖：`175 × 175` 页面单位
- 语义比例：`11.702857142857143 px/页面单位`
- 内置图像工具实际结果：统一归一为 `1254 × 1254 px`
- 成品比例：`7.1657142857142855 px/页面单位`

禁止复用旧 `1024` mask、按包围盒重新居中，或把成品横向/纵向拉伸到旧 tile bounds。

## 2. 逐次维护联合语义 SVG

联合语义 SVG 是连续地理语义的唯一来源。单区划 SVG 只在首次加入时提供内部初稿，之后不能单独决定公共边界。

加入新区划时：

1. 把新区划初稿放入 balanced page space。
2. 冻结已验收区划远离新接缝的内部语义。
3. 在共享边界建立 join collar；河湖、农田、聚落和山地在 collar 内由 join 统一拥有。
4. 检查河流端点、湖岸、山地密度和都市区域是否连续，避免行政边界造成直线截断。
5. 更新 `artwork/semantic-joint-state.json`，再生成新的联合主 SVG。

水文必须先合成一个 `water-surface`。深色河流提示层需要减去湖泊内部，湖中不得继续出现河线。

当前主文件：`dist/assets/joint-nanchang-jiujiang/nanchang-jiujiang-joint-semantic-v7.svg`。

## 3. 生成固定比例窗口计划

```bash
.venv/bin/python scripts/build_fixed_scale_generation_tiles.py REGION_ID
```

脚本产生 `artwork/generation-inputs/<region>/fixed-scale-tiles/<region>-plan.json`，包含：

- canonical path 与精确 bounds
- 每个窗口的 `worldBounds`
- 生成顺序
- 重叠区所有权
- context、可见 mask 与 edit mask 路径

区划放不进一个窗口时增加窗口数量。后续窗口只锁定前序窗口拥有的半个重叠区，避免两次生成都改写同一片像素。

## 4. 构造 context 与 mask

图像工具的输入固定为两张图：

- 图 1 `context.png`：目标区划的联合语义；已生成邻区插入其最终底图；只有 SVG 的邻区插入联合语义；没有 SVG 的区域保持纸色空白。
- 图 2 `mask.png`：纯白像素必须生成，纯黑像素不可编辑。已验收邻区和前序窗口拥有的重叠区必须是黑色。

加入邻区成品：

```bash
.venv/bin/python scripts/build_fixed_scale_generation_tiles.py TARGET_ID \
  --neighbor-art NEIGHBOR_ID=PATH_TO_CANONICAL_ART
```

加入已验收前序窗口：

```bash
.venv/bin/python scripts/build_fixed_scale_generation_tiles.py TARGET_ID \
  --accepted-window 1=PATH_TO_RESTORED_WINDOW_01
```

邻区成品只能按其 canonical page bounds 放置并裁切，不能重新缩放到“看起来接近”的位置。

## 5. 分窗口调用图像生成

每个窗口独立调用图像工具，同时传入 context 和 mask。使用 `artwork/prompts/base.md`，再附加一个且仅一个窗口区域配置。

核心语义：

- 白色 mask 内必须全部转换为完整底图，不能残留灰色语义块。
- 黑色 mask 外尽量保持不变；最终仍会逐像素恢复。
- 蓝色是开放水面的最大范围；所有非蓝色区域必须是干燥陆地。
- 建筑和道路纹理只能出现在灰色聚落区域。
- 黄色只生成农田，绿色只生成山林或乡野。
- 地标由红色定位点和文本描述共同约束，生成后定位点消失。
- 无文字、标签、边界线、图钉、额外地标、装饰村庄和沼泽扩张。

同一城市的不同窗口允许并且经常需要不同提示词；固定的是技术约束与画风，不是地理内容。

## 6. 确定性恢复、合并与裁切

生成器不能保证参考区像素完全不变，因此每个 raw 窗口必须执行：

```bash
.venv/bin/python scripts/restore_fixed_scale_locked_pixels.py \
  RAW.png CONTEXT.png MASK.png RESTORED.png
```

黑色 mask 对应的像素从 context 原样恢复。然后按 plan 合并：

```bash
.venv/bin/python scripts/merge_fixed_scale_region_windows.py \
  PLAN.json CANONICAL.png \
  --window 1=WINDOW_01_RESTORED.png \
  --window 2=WINDOW_02_RESTORED.png
```

单窗口和多窗口最终都裁到 `canonicalPathBounds` 并保留 alpha；不得使用旧 padded bounds。

## 7. 验收标准

发布前至少检查：

- canonical 外轮廓与网页 balanced path 一致。
- 与已完成邻区的河流、湖岸、农田尺度、笔触和色温连续。
- 非蓝区域没有开放水面或模糊沼泽。
- 湖泊内部没有深色河线。
- 都市、县城仅位于灰色语义区，乡野没有散落建筑。
- 县级或相近规模聚落清晰，但密度符合当地实际。
- 每个相对独立区域最多一个地标，位置关系正确。
- 无文字、语义色块、定位点、行政描边和调试标记。
- 多窗口接缝在正常浏览比例下不可辨认。

联合审阅图可用：

```bash
.venv/bin/python scripts/build_fixed_scale_canonical_review.py REVIEW.png \
  --region PLAN_A.json=CANONICAL_A.png \
  --region PLAN_B.json=CANONICAL_B.png
```

## 8. 发布

1. canonical PNG 转为带 alpha 的版本化 WebP，建议小于 `600 KB`。
2. `dist/jiangxi-city-tiles.json` 的 `bounds` 必须等于 plan 的 `canonicalPathBounds`。
3. `image` 使用新版本文件名，避免 CDN 命中旧资源。
4. 执行工作流校验：

```bash
.venv/bin/python scripts/validate_region_art.py artwork/workflows/<region>.json
```

5. 在完整页面的艺术地图、面积均衡模式中检查真实加载的资源 URL 与 bounds。

正式页面只保留当前版本的 WebP；旧版本由 Git 历史保存，不继续堆放在 `dist`。

## 资产保留策略

| 类型 | 是否提交 | 生命周期 |
|---|---:|---|
| 联合语义 SVG、联合状态 | 是 | 持续演进，始终保留最新版本 |
| 单区划 semantic SVG、mask、manifest | 是 | 长期保留 |
| 固定比例配置、plan、提示词、workflow JSON | 是 | 长期保留，作为复现记录 |
| context、mask PNG | 否 | 可重新生成的中间产物 |
| raw 与 rejected 图 | 否 | 验收结束后删除 |
| restored 窗口 | 否 | canonical 合并完成后可删除 |
| canonical PNG | 可选 | 本地审阅源；正式仓库以 WebP 为准 |
| 当前版本 WebP | 是 | 页面唯一加载资产 |
| 旧版 WebP | 否 | 从工作树删除，由 Git 历史追溯 |

## 可复用与必须调整

始终复用：balanced 坐标链、固定比例配置、联合语义机制、窗口规划、二值 mask、锁定像素恢复、合并、canonical 裁切、QA 和发布检查。

每个目标必须调整：真实地理资料、语义 SVG 内部、区域地貌与农田类型、聚落锚点与形态、地标、窗口区域提示词、已验收邻区列表和生成顺序。

当前验收版本与校验和记录在 `artwork/accepted-generation.json`。

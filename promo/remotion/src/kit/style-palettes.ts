// ─────────────────────────────────────────────────────────────
// 风格色板库 — 来源：341 种代码动画风格提示词（UP主俯仰观照开源）
// 341 styles from BV1bqx76wEUM · 夸克网盘分享 · 2026-10-28
// 仅提取色板和字体搭配，提示词原文见 KB: 01-Raw/Bilibili/341-style-prompts-code-animation.md
// 完整风格库：01-Projects/bilibili_audio/341-styles/extracted/
// 注意：L/V/X 类为开源项目，保留原许可；A-G/R/M/K/Z/H/O 为 UP主整理，禁止包装卖课
// ─────────────────────────────────────────────────────────────

export interface StylePalette {
  name: string;
  source: string;  // 来源分类
  colors: string[]; // hex 色值
  desc?: string;    // 风格描述
}

export const STYLE_PALETTES: StylePalette[] = [
  {
    name: "O11 浮生若梦 (You Can't Take It with You)",
    source: "O",
    colors: [#F0E2C0, #E0A842, #C84A2A, #22686E, #D97757, #322018],
    desc: "30 年代 WPA 丝网海报：六色不透明平涂油墨、分色渐变、轻微套印错位，印在棉浆纸上。1936–39 年联邦艺术计划的",
  },
  {
    name: "O15 忠勇之家 (Mrs. Miniver)",
    source: "O",
    colors: [#EBDFC2, #8497A6, #A23F2D, #34503F, #1E2422],
    desc: "二战英国本土战线的石印海报：砖红、深绿、奶油、灰蓝的有限套色，阴影是石版蜡笔颗粒。配影片结尾：被炸穿屋顶的乡村教堂里全村",
  },
  {
    name: "O22 国王班底 (All the King's Men)",
    source: "O",
    colors: [#EEE3C7, #20488C, #C82C28, #1E1B1E, #D97757],
    desc: "南方竞选海报的木活字凸版：红、蓝、黑三色油墨印在米黄纸上，实地有木纹，供墨不匀，版间错位，肖像走半调网点。这是斯塔克的竞",
  },
  {
    name: "O27 码头风云 (On the Waterfront)",
    source: "O",
    colors: [#768492, #9E4834, #C89852, #1F1A1A, #F0E9DA, #D97757],
    desc: "本·沙恩的社会现实主义：颤抖的转印墨线，下面是错开的平涂蛋彩色块，大手长脸的工人，颜色克制在灰蓝、砖红、赭黄。沙恩画的就",
  },
  {
    name: "O30 桂河大桥 (The Bridge on the River Kwai)",
    source: "O",
    colors: [#143874, #ECF4FF, #D63426, #D97757],
    desc: "钉在绘图桌上的总布置图：普鲁士蓝底上的白线、折痕、水渍和红铅笔修改。电影讲一个执意把桥造好的上校，所以把桥画成他的工程图",
  },
  {
    name: "O35 阿拉伯的劳伦斯 (Lawrence of Arabia)",
    source: "O",
    colors: [#1F4D97, #A9C3D6, #EEC27A, #B56A33, #6C6394],
    desc: "看得见笔触方向的史诗海报水粉，冷暖对比强烈：琥珀色沙漠对钴蓝天空。《阿拉伯的劳伦斯》原海报就是 Howard Terpn",
  },
  {
    name: "O39 日月精忠 (A Man for All Seasons)",
    source: "O",
    colors: [#1F4A26, #141113, #6E0C15, #B0801E, #3E2818],
    desc: "古典大师油画肖像：平滑罩染塑形、一根根画出的毛领、天鹅绒高光、逐环刻画的金链，再加旧光油和龟裂纹。霍尔拜因 1527 年",
  },
  {
    name: "O42 午夜牛郎 (Midnight Cowboy)",
    source: "O",
    colors: [#F3BE14, #F2A197, #EFE6CF, #E2462B, #BABCC0],
    desc: "沃霍尔的照片丝网：黑色网点照片层印得不匀，错位地压在松散的平涂色块上，底是银色，画面重复两次、三次。片里就有沃霍尔工厂式",
  },
  {
    name: "O45 教父 (The Godfather)",
    source: "O",
    colors: [#24150B, #070403, #8F5D2A, #E2B673, #9C1A1A],
    desc: "深琥珀和赭褐的油画，只有顶光落下的地方是暖的：暗部是透明的薄罩染，受光边缘是厚涂。重现戈登·威利斯在“I believe",
  },
  {
    name: "O48 飞越疯人院 (One Flew Over the Cuckoo's Nest)",
    source: "O",
    colors: [#9EB8A0, #5E7C66, #7E8876, #ECE6D2, #FCE6AC],
    desc: "仿爱德华·霍珀的安静写实：大块平整的淡绿墙面、低角度晨光投下的硬边平行四边形、彼此隔开的人。正合《飞越疯人院》的病房：日",
  },
  {
    name: "O50 安妮·霍尔 (Annie Hall)",
    source: "O",
    colors: [#9698A0, #78A0BE, #E2CCA0, #C45C32, #FBF8F1],
    desc: "《纽约客》单格漫画：灵动的钢笔墨线、几块克制的淡彩、大量白纸，画下面一行手写图说。伍迪·艾伦的喜剧和这本杂志是一个调子，",
  },
  {
    name: "O53 普通人 (Ordinary People)",
    source: "O",
    colors: [#ECAA34, #E46030, #B8743C, #C2C6D2, #8A8496],
    desc: "层层叠色的透明水彩：湿画法的天空和湖面、水渍边线、回流花、留白的纸当高光，秋天的金和锈红配上冷灰蓝。对上影片开场那个安静",
  },
  {
    name: "O57 莫扎特传 (Amadeus)",
    source: "O",
    colors: [#0B0705, #F7E3A0, #B88A2E, #6E0F14, #0C1A3A],
    desc: "黑纸剪成的侧面人像镶着金边，坐满马蹄形的金色包厢和红丝绒，对着星空布景的舞台。《莫扎特传》的高光是首演之夜，一个画面装下",
  },
  {
    name: "O61 雨人 (Rain Man)",
    source: "O",
    colors: [#79BDA6, #F58CB5, #C9467F, #56E6FF, #D9FBFF],
    desc: "平滑的喷枪渐变、硬边遮罩、镀铬高光和粉绿霓虹，叠一层细细的青色计数标注。80 年代画风配上雷蒙眼里的世界：82、82、8",
  },
  {
    name: "O64 沉默的羔羊 (The Silence of the Lambs)",
    source: "O",
    colors: [#EFE3C4, #5A3A22, #B4431E, #E6AD24, #7D6F8E],
    desc: "细密的铜版排线和点刻，上面薄薄地手工上色，图版编号和拉丁文标签印在泛黄的纸上。海报上的鬼脸天蛾本就该钉在标本图版上，同样",
  },
  {
    name: "O69 英国病人 (The English Patient)",
    source: "O",
    colors: [#E8D6B0, #6B4A2E, #D08A3C, #9C6A86, #2A1E16],
    desc: "贴在旧书里的水彩速写，夹着地图、照片、便条和压花，整体是海报的琥珀褐。艾玛殊那本塞满画和笔记的希罗多德是全片的框架，镜头",
  },
  {
    name: "O71 莎翁情史 (Shakespeare in Love)",
    source: "O",
    colors: [#203E92, #D6B05C, #A8202C, #F6F2E8, #346C40],
    desc: "学尼古拉斯·希利亚德的伊丽莎白时代宫廷细密画：羊皮纸上的不透明水彩、群青底、贝壳金题字、白色野蔷薇。影片发生在莎士比亚的",
  },
  {
    name: "O75 芝加哥 (Chicago)",
    source: "O",
    colors: [#D0202A, #FF5A3C, #FFD9A0, #FFF1D6],
    desc: "黑色舞台被硬边聚光切开：六间牢房里是勾红边的女囚剪影，背后霓虹 C，亮片和烟雾，Clawd 在白色追光里。这是电影版的「",
  },
  {
    name: "O79 无间行者 (The Departed)",
    source: "O",
    colors: [#151312, #8C8A85, #C99A2E, #C3261F, #7A3224],
    desc: "平涂的多层喷漆模板，有喷雾毛边和流挂，漆吃进砖缝，旁边一张撕破的糊贴海报。《无间行者》最后一个镜头是老鼠爬过州议会金顶下",
  },
  {
    name: "O85 逃离德黑兰 (Argo)",
    source: "O",
    colors: [#1696CD, #DE2C70, #FFD616, #1C161A, #EEE2C2],
    desc: "摊在制片桌上的 70 年代柯比漫画：粗墨线、柯比能量泡、泛黄新闻纸上的四色网点。片中那部假科幻片用的正是柯比画的概念图，",
  },
  {
    name: "O88 聚焦 (Spotlight)",
    source: "O",
    colors: [#1b2320, #0c110f, #a0dcaf, #D97757],
    desc: "印成报纸网点的画面，放到缩微胶片阅读机的灰绿屏幕上：扫描线、滚动的扫描光带、玻璃上的灰尘。片中记者就在这种档案里挖出真相",
  },
  {
    name: "O90 水形物语 (The Shape of Water)",
    source: "O",
    colors: [#041414, #5fb3a6, #0c2a24],
    desc: "实时 3D 的被淹浴室和实验室水箱，整片浸在青绿里：流动的焦散、从上方落下的光束、气泡和几盏暖色灯。德尔·托罗这部片就泡",
  },
  {
    name: "O93 无依之地 (Nomadland)",
    source: "O",
    colors: [#7d7079, #f6cf7a, #c9738a, #4b3f78, #2b2d5c],
    desc: "灰紫色纸上的粉质色粉笔触，一片开阔的平原和一辆旧房车，天空从金黄变成玫瑰色再到紫色。《无依之地》就活在黄昏那条又长又空的",
  },
  {
    name: "O96 奥本海默 (Oppenheimer)",
    source: "O",
    colors: [#ff9a50, #ffd8a0, #2a3654, #16120e],
    desc: "用实时 3D 重建黎明前的三位一体试验场：约 72 万粒子的火球、轨道和波组成的量子幻象，深蓝夜色对橙金火光，加 IMA",
  },
  {
    name: "X11 翻牌显示板 (Split-flap board)",
    source: "X",
    colors: [#0f0f10, #232326, #f1ede2, #ffb000, #39d353, #ff5a4f],
  },
  {
    name: "X14 CRT 终端 (CRT terminal)",
    source: "X",
    colors: [#031208, #46ff8a, #ffc24a],
  },
  {
    name: "X19 纪录片 (Documentary)",
    source: "X",
    colors: [#000000, #E8DED2, #D07152, #96473C, #D5CAB4, #403D38],
  },
  {
    name: "X28 组装说明书 (Assembly manual)",
    source: "X",
    colors: [#F0EEE4, #E1DDD1, #191A18, #E4E0D1, #CCC6B6, #F4D7CA, #D0643A],
  },
  {
    name: "X3 沙画 (Sand art)",
    source: "X",
    colors: [#f3dcae, #9b7648, #2e2014],
  },
  {
    name: "X6 界面形变 (UI morph)",
    source: "X",
    colors: [#ecebe7, #0b0b0b, #ffffff, #8d8c88],
  },
];

// ─────────────────────────────────────────────────────────────
// H 类：配色+字体版式（12 组，短描述型）
// ─────────────────────────────────────────────────────────────

export interface StyleFontCombo {
  name: string;
  fontStack: string[]; // 推荐字体栈
  desc: string;
  source: string;
}

export const STYLE_FONT_COMBOS: StyleFontCombo[] = [
  { name: "H10 Creative Mode", fontStack: [], desc: "奶油底，饱和糖果色，Archivo Black 大字", source: "H" },
  { name: "H11 Daisy Days", fontStack: [], desc: "阳光花园粉彩，3px 炭灰描边，硬投影，圆体字", source: "H" },
  { name: "H12 Editorial Forest", fontStack: [], desc: "绿、粉、奶油的杂志配色，衬线标题，细线", source: "H" },
  { name: "H1 Biennale Yellow", fontStack: [], desc: "暖羊皮纸底，太阳黄光晕，衬线大标题，靛蓝墨色，细线", source: "H" },
  { name: "H2 BlockFrame", fontStack: [], desc: "新粗野主义，粗黑边框，硬投影，糖果色点缀", source: "H" },
  { name: "H3 Blue Professional", fontStack: [], desc: "羊皮纸底，钴蓝主色，Space Grotesk 标题", source: "H" },
  { name: "H4 Bold Poster", fontStack: [], desc: "倾斜的花体大字，奶油底红色强调，杂志封面感", source: "H" },
  { name: "H5 Broadside", fontStack: [], desc: "工业报纸海报，奶油色配墨色，火橙色点缀", source: "H" },
  { name: "H6 Capsule", fontStack: [], desc: "胶囊形状，奶油纸，糖果配色，Bodoni 衬线标题", source: "H" },
  { name: "H7 Cartesian", fontStack: [], desc: "极简留白，暖羊皮纸，墨色标题，灰褐点缀，细线", source: "H" },
  { name: "H8 Cobalt Grid", fontStack: [], desc: "羊皮纸加钴蓝网格，Newsreader 标题", source: "H" },
  { name: "H9 Coral", fontStack: [], desc: "全大写 Bebas Neue 标题，奶油底珊瑚色", source: "H" },
];

/**
 * 按名称查找色板
 * @param name 风格名称（支持模糊匹配）
 * @returns 匹配的色板，未找到返回 null
 */
export const findPalette = (name: string): StylePalette | null => {
  const lower = name.toLowerCase();
  return STYLE_PALETTES.find(p =>
    p.name.toLowerCase().includes(lower) || lower.includes(p.name.toLowerCase().split('_')[0])
  ) ?? null;
};
// 产品层口袋口径（2026-09-16 用户口径）收敛点：引擎 PatternOptions 默认
// 最小裸版（口袋族关），Web 侧显式开 front_pocket/front_pocket_facing——
// 牛仔裤挖削前口袋+袋贴是标配（useDraft 存量草稿补键同源消费）。
// 出厂参数合成 buildFactoryValues 2026-09-20 随「空白默认 = 直筒基样
// toml 直接载入」口径退役（git 史留档），本文件只剩键清单单源。

// 产品层显式开的口袋族键（useDraft 存量补键同源消费，键清单单源）
export const PRODUCT_POCKET_KEYS = ['front_pocket', 'front_pocket_facing'] as const

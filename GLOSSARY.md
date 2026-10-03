# 地质体建模 — 领域术语表

## Session（会话）
用户上传一个钻孔数据文件后到该数据被清理前的完整生命周期。每个 session 由 8 字符 UUID 标识，包含一个上传的 Excel 文件和所有由此产生的生成结果（钻孔视图、建模图、AI 生成图等）。Session 在一段时间无活动后过期，其所有数据被清理。

## 临时数据（Temporary Data）
Session 生命周期内产生的所有生成结果（图片、HTML、缓存元数据等）。临时数据随 session 过期而删除，用户如需保留必须主动下载。

## 已下载数据（Downloaded Data）
用户通过"下载当前图"或"下载全部"按钮保存到本地的文件。下载后不再受 session 生命周期管理影响。

## 过期（Expiration）
Session 在 60 分钟无任何 API 请求后变为过期状态，触发清理：删除该 session 的 outputs/ 子目录和 uploads/ 子目录。

## 活跃跟踪（Activity Tracking）
系统通过记录每个 session_id 的最后一次 API 调用时间来判断 session 是否活跃。每次携带 session_id 的请求都会更新时间戳。

## 输出分组（Output Grouping）
所有生成结果按 session 存放在 `outputs/{session_id}/` 子目录下，而非之前的平铺式根目录结构。URL 也相应包含 session_id 路径段。

## 新建会话（New Session）
用户主动清理当前 session 并重新开始的机制。通过左侧控制面板的按钮触发，或上传新文件时自动触发。
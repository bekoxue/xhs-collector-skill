# 输出字段说明

各命令输出 JSON 文件中 `records` 的字段（`fields` 数组给出 key→中文名映射，CSV 表头即中文名）。

## image_note（note / enrich 命令）

| key | 名称 |
|---|---|
| `note_id` | 笔记ID |
| `title` | 标题 |
| `desc` | 正文 |
| `note_type` | 类型 |
| `note_url` | 链接 |
| `author_nickname` | 博主 |
| `author_id` | 博主ID |
| `author_red_id` | 小红书号 |
| `liked_count` | 点赞数 |
| `collected_count` | 收藏数 |
| `comment_count` | 评论数 |
| `share_count` | 分享数 |
| `image_count` | 图片数 |
| `cover` | 封面 |
| `images` | 图片附件 |
| `video_url` | 视频链接 |
| `video_file` | 视频附件 |
| `video_duration` | 视频时长(秒) |
| `video_resolution` | 视频分辨率 |
| `video_size_mb` | 视频大小(MB) |
| `tags` | 标签 |
| `ip_location` | IP属地 |
| `publish_time` | 发布时间 |
| `collected_at` | 采集时间 |

## user_info（user-info 命令）

| key | 名称 |
|---|---|
| `user_id` | 用户ID |
| `nickname` | 昵称 |
| `red_id` | 小红书号 |
| `desc` | 简介 |
| `gender` | 性别 |
| `ip_location` | IP属地 |
| `avatar` | 头像 |
| `banner` | 主页背景图 |
| `follows` | 关注数 |
| `fans` | 粉丝数 |
| `liked` | 获赞数 |
| `collected` | 收藏数 |
| `interaction` | 获赞与收藏 |
| `note_count` | 笔记数 |
| `board_count` | 收藏专辑数 |
| `level` | 等级 |
| `tags` | 标签 |
| `is_verified` | 是否认证 |
| `verify_content` | 认证信息 |
| `profile_url` | 主页链接 |
| `collected_at` | 采集时间 |

## user_notes（user-notes 命令）

| key | 名称 |
|---|---|
| `note_id` | 笔记ID |
| `title` | 标题 |
| `desc` | 正文摘要 |
| `note_type` | 类型 |
| `note_url` | 链接 |
| `cover` | 封面 |
| `liked_count` | 点赞数 |
| `collected_count` | 收藏数 |
| `comment_count` | 评论数 |
| `share_count` | 分享数 |
| `author_nickname` | 博主 |
| `author_id` | 博主ID |
| `tags` | 标签 |
| `publish_time` | 发布时间 |
| `desc_full` | 完整正文 |
| `images` | 图片附件 |
| `ip_location` | IP属地 |
| `author_red_id` | 小红书号 |
| `video_url` | 视频链接 |
| `video_file` | 视频附件 |
| `video_duration` | 视频时长(秒) |
| `video_resolution` | 视频分辨率 |
| `video_size_mb` | 视频大小(MB) |
| `detail_synced` | 已采详情 |
| `collected_at` | 采集时间 |

## search_notes（search 命令）

| key | 名称 |
|---|---|
| `note_id` | 笔记ID |
| `title` | 标题 |
| `desc` | 正文摘要 |
| `note_type` | 类型 |
| `note_url` | 链接 |
| `cover` | 封面 |
| `liked_count` | 点赞数 |
| `collected_count` | 收藏数 |
| `comment_count` | 评论数 |
| `share_count` | 分享数 |
| `author_nickname` | 博主 |
| `author_id` | 博主ID |
| `author_avatar` | 博主头像 |
| `tags` | 标签 |
| `publish_time` | 发布时间 |
| `keyword` | 搜索词 |
| `desc_full` | 完整正文 |
| `images` | 图片附件 |
| `ip_location` | IP属地 |
| `author_red_id` | 小红书号 |
| `video_url` | 视频链接 |
| `video_file` | 视频附件 |
| `video_duration` | 视频时长(秒) |
| `video_resolution` | 视频分辨率 |
| `video_size_mb` | 视频大小(MB) |
| `detail_synced` | 已采详情 |
| `collected_at` | 采集时间 |

## topic_notes（topic 命令）

| key | 名称 |
|---|---|
| `note_id` | 笔记ID |
| `title` | 标题 |
| `desc` | 正文摘要 |
| `note_type` | 类型 |
| `note_url` | 链接 |
| `cover` | 封面 |
| `liked_count` | 点赞数 |
| `collected_count` | 收藏数 |
| `comment_count` | 评论数 |
| `share_count` | 分享数 |
| `author_nickname` | 博主 |
| `author_id` | 博主ID |
| `tags` | 标签 |
| `publish_time` | 发布时间 |
| `desc_full` | 完整正文 |
| `images` | 图片附件 |
| `ip_location` | IP属地 |
| `author_red_id` | 小红书号 |
| `video_url` | 视频链接 |
| `video_file` | 视频附件 |
| `video_duration` | 视频时长(秒) |
| `video_resolution` | 视频分辨率 |
| `video_size_mb` | 视频大小(MB) |
| `detail_synced` | 已采详情 |
| `topic_name` | 话题名称 |
| `topic_page_id` | 话题页面ID |
| `topic_sort` | 话题排序 |
| `collected_at` | 采集时间 |

## comments（comments / replies 命令）

| key | 名称 |
|---|---|
| `comment_id` | 评论ID |
| `note_id` | 笔记ID |
| `content` | 评论内容 |
| `like_count` | 点赞数 |
| `author_nickname` | 评论者 |
| `author_id` | 评论者ID |
| `ip_location` | IP属地 |
| `create_time` | 评论时间 |
| `sub_comment_count` | 回复数 |
| `is_reply` | 是否回复 |
| `parent_comment_id` | 父评论ID |
| `reply_to` | 回复对象 |
| `collected_at` | 采集时间 |

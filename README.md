# wechat-year-report 
本工具由AI制作
用 Python 解析「微信聊天记录导出 TXT」，生成可离线打开的年度总结 HTML（包含：消息趋势图、活跃时段、Top 发言者、高频词、表情 Top、词云等）。

> 本项目不负责导出微信聊天记录；只负责分析你已经导出的 TXT 文件。

 功能概览

- ✅ 支持两种模式
  - 单文件分析：只分析某一个聊天（可为单人或群聊）
  - 目录汇总分析：递归扫描目录下所有 `.txt`，合并统计生成汇总报告
- ✅ 可按年份过滤：`--year 2025`
- ✅ 输出为 自包含 HTML（图表与词云会转为 base64 内嵌，双击即可打开）
- ✅ 基础去噪：过滤撤回提示、XML 残留、链接、wxid/uuid/长 hex 等噪声
- ✅ 中文分词：jieba + 停用词，支持统计类似 `[doge]` 的表情占位符

 环境要求

- Python 3.9+（建议 3.10/3.11）
- 依赖库：
  - `pandas`
  - `matplotlib`
  - `jieba`
  - `wordcloud`

 安装依赖

```bash
pip install pandas matplotlib jieba wordcloud
（可选）你也可以把下面内容保存为 requirements.txt：
pandas
matplotlib
jieba
wordcloud
然后：
pip install -r requirements.txt
 
输入TXT格式要求：
- 脚本按以下格式解析消息行（每条消息一行）：
[2025-02-01 16:34:42] wxid_a -> wxid_b: 这里是消息内容
支持多行消息：如果某行不匹配消息格式，会被当作上一条消息的续行拼接进去。
可选的文件头元信息（用于把 with_id 映射成昵称/群名展示）：
聊天对象：张三
with_id：wxid_xxxxxxx
----------
[2025-02-01 16:34:42] ...
如果你的 TXT 是别的导出工具生成、格式不同：需要改 RE_LINE 这条正则，或贴一小段样例我来帮你对齐。
 
 使用方法：
- 1) 单文件分析（推荐先试这个）
python wechat_year_report.py \
  --dir "/path/to/txt_root" \
  --file "某个聊天.txt" \
  --year 2025 \
  --outdir "/path/to/out"
•	--dir：TXT 根目录（用于辅助查找 --file 的文件名）
•	--file：只分析某一个 TXT（可传完整路径或文件名）
•	--year：只统计某一年（不填则统计全部）
•	--outdir：输出目录（默认桌面 ~/Desktop/wechat_year_report/out）
运行成功后会输出：
•	out/index.html（入口）
•	out/report_SINGLE_xxx_2025.html（报告）
 
2) 全目录汇总（统计你导出的全部会话）
python wechat_year_report.py \
  --dir "/path/to/txt_root" \
  --year 2025 \
  --outdir "/path/to/out"
它会递归扫描 --dir 下所有 .txt 并合并统计，输出：
•	out/report_ALL_2025.html
•	out/index.html
 
 统计说明：
- •	“消息总数 / 每天消息量 / 每小时活跃”均基于所有收发消息（包含你发出的 + 你收到的）。
•	“最长连续聊天天数”：按“有消息的日期”做连续天数统计；只要某天完全没消息就会断开。
 
 词云生成说明（中文字体）：
```词云需要中文字体。脚本会尝试在 macOS 常见路径里自动找字体（Songti/PingFang）。
如果你在 Windows/Linux 上运行，可能会提示无法生成词云：请把 pick_font() 改成你系统字体路径，例如：
•	Windows：C:\Windows\Fonts\msyh.ttc（微软雅黑）
•	Linux：安装中文字体后填对应路径
 
 已知问题 & 待优化：
- •	少量情况下，可能会把某些 用户 ID / 系统字段误当作聊天内容（可继续完善过滤规则）
•	不同导出工具的 TXT 格式可能不一致，需要调整解析正则 RE_LINE
•	群聊昵称映射目前只依赖文件头元信息，可能不完整
 
 隐私与安全提醒（强烈建议阅读）：
- •	聊天记录属于敏感数据：建议全程离线本地处理。
•	不要把原始 TXT、生成的报告 HTML 直接上传到公开仓库或公开网页。
•	涉及他人隐私请先征得同意；公开展示建议先做脱敏（匿名化用户名、过滤人名/手机号/地址等）。
 
 相关工具 / 致谢：
- •	微信聊天记录导出工具（iOS 备份解析）：WechatExporter
•	https://github.com/BlueMatthew/WechatExporter
•	分词：jieba
•	词云：wordcloud
•	绘图：matplotlib
•	数据处理：pandas

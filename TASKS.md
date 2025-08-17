# ToImage 插件目标任务

- [x] 在 ToImage 插件中新增 NormalMessageResponded 事件处理器，当 AI 回复包含'测试'时，将发送内容改为'收到'
- [x] 修改：当 AI 回复包含 Markdown 图片（例如：测试![描述](图片链接)）时，下载图片并与文本按原顺序组合为消息链发送
- [ ] 重启服务并测试插件功能（包括 Markdown 图片消息链构建），验证"测试"文本被正确拦截和替换为"收到"
- [ ] 发布插件到GitHub仓库 https://github.com/yumo666666/ToImage.git

> 说明：此文件用于记录本插件的开发目标与完成情况，后续若有新需求将持续追加并打勾标记。
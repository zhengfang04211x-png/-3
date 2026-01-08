# 企业套保运营分析系统

一个基于Streamlit的Web应用，用于分析企业套期保值运营数据，生成专业的报表和可视化图表。

## 功能特点

- 📊 **数据可视化**: 自动生成4类专业分析图表
- 💰 **资金管理**: 实时监控账户权益和资金安全通道
- 📈 **对冲效果分析**: 对比套保前后的资产价值波动
- 📋 **Excel报表**: 一键下载详细的运营日报
- ⚙️ **参数可配置**: 灵活调整业务参数和风险参数

## 快速开始

### 本地运行

1. **安装依赖**
```bash
pip install -r requirements.txt
```

2. **运行应用**
```bash
streamlit run app.py
```

3. **访问应用**
在浏览器中打开显示的本地地址（通常是 http://localhost:8501）

### 部署到云端

#### 方法1: Streamlit Cloud（推荐）

1. 将代码推送到GitHub仓库
2. 访问 [Streamlit Cloud](https://streamlit.io/cloud)
3. 连接GitHub账户，选择仓库
4. 点击"Deploy"即可自动部署

#### 方法2: 其他云平台

- **Heroku**: 需要添加 `Procfile` 和 `runtime.txt`
- **AWS/阿里云**: 使用ECS或Lambda部署
- **Docker**: 可以容器化部署

### Docker部署（可选）

创建 `Dockerfile`:
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

构建和运行:
```bash
docker build -t hedging-app .
docker run -p 8501:8501 hedging-app
```

## 数据格式要求

CSV文件需要包含以下列：

1. **日期列**: 列名包含"时间"或"Date"
2. **现货价格列**: 列名包含"现货"
3. **期货价格列**: 列名包含"期货"或"主力"，且包含"价格"

示例CSV格式：
```csv
日期,现货价格,期货主力价格
2023-01-01,50000,49500
2023-01-02,50500,49800
...
```

## 参数说明

### 业务参数
- **库存量**: 现货库存数量（吨）
- **套保比例**: 套期保值比例（0-2倍）
- **保证金率**: 期货保证金率（通常0.1-0.15）

### 资金管理
- **补金线倍数**: 账户权益低于此倍数需补金
- **提金线倍数**: 账户权益高于此倍数可提金

### 风险参数
- **持仓天数**: 用于计算周期性风险的持仓周期

## 生成的报表内容

1. **图1**: 期现价格走势与基差监控
2. **图2**: 资产波动分布对比
3. **图3**: 资金安全通道监控
4. **图4**: 账面资产价值变动对比

Excel报表包含：
- 日期、现货单价、期货单价、基差
- 占用保证金、账户权益、风险度
- 补金线、提金线
- 当日需补金、当日可出金
- 套保后净值变动

## 技术栈

- **Streamlit**: Web应用框架
- **Pandas**: 数据处理
- **Matplotlib/Seaborn**: 数据可视化
- **OpenPyXL**: Excel文件生成

## 注意事项

- 确保CSV文件编码正确（支持GBK和UTF-8）
- 日期格式需要能被pandas识别
- 价格数据应为数值类型
- 建议数据量不超过10万行以确保性能

## 许可证

MIT License

## 联系方式

如有问题或建议，欢迎提交Issue或Pull Request。

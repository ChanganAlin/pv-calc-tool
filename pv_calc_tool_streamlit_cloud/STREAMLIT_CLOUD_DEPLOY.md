# Streamlit Community Cloud 部署步骤

本工具是 `Python + Streamlit` 应用，推荐部署到 Streamlit Community Cloud。部署后会得到一个公网 HTTPS 链接，可以直接发微信给别人打开。

## 1. 准备 GitHub 仓库

1. 登录 GitHub。
2. 新建一个仓库，例如：

```text
pv-calc-tool
```

3. 上传 `pv_calc_tool` 目录下的全部文件。

需要包含：

```text
app.py
requirements.txt
packages.txt
.streamlit/config.toml
assets/
components/
config/
data/
modules/
sample_data/
templates/
```

## 2. 部署到 Streamlit Community Cloud

1. 打开 Streamlit Community Cloud。
2. 选择 New app。
3. 连接 GitHub 仓库。
4. 设置：

```text
Repository: 你的 GitHub 仓库
Branch: main
Main file path: app.py
```

5. 点击 Deploy。

部署成功后，会得到类似下面的链接：

```text
https://你的应用名.streamlit.app
```

这个链接可以直接发微信。

## 3. 部署注意事项

1. 免费版应用可能会休眠，首次打开可能较慢。
2. 如果上传电费单、屋顶截图等敏感资料，不建议公开分享链接。
3. 正式内部使用建议增加登录密码或改为公司服务器部署。
4. OCR 依赖已经写入 `packages.txt`，包括：

```text
tesseract-ocr
tesseract-ocr-chi-sim
```

5. 云端已使用 `opencv-python-headless`，避免 Linux 部署时缺少图形库导致失败。

## 4. 本地测试

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 5. 微信分享

部署成功后，直接复制 Streamlit Cloud 给出的 `https://...streamlit.app` 链接，发给微信好友即可。

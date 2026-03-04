# API 参考文档

地质图自动转换工具 REST API 文档。

## 基础信息

- **Base URL**: `http://localhost:8000`
- **Content-Type**: `application/json` 或 `multipart/form-data`
- **WebSocket URL**: `ws://localhost:8000/ws/{task_id}`

## API 端点

### 1. 文件上传

#### 上传地质图文件

```http
POST /api/upload/image
Content-Type: multipart/form-data
```

**请求参数:**
- `file`: 文件对象（必需）

**响应 (200):**
```json
{
  "task_id": "uuid-v4",
  "filename": "map.png",
  "status": "pending",
  "file_path": "uploads/uuid-v4.png"
}
```

**错误响应 (400):**
```json
{
  "detail": "Only PNG, JPEG, and PDF files are supported"
}
```

---

### 2. 任务状态

#### 获取任务状态

```http
GET /api/upload/task/{task_id}
```

**响应 (200):**
```json
{
  "task_id": "uuid-v4",
  "filename": "map.png",
  "status": "processing",
  "progress": 0.5,
  "error_message": null
}
```

**状态值:**
- `pending`: 等待处理
- `processing`: 处理中
- `completed`: 已完成
- `failed`: 失败

---

### 3. 地理配准

#### 提交控制点

```http
POST /api/registration/submit
Content-Type: application/json
```

**请求体:**
```json
{
  "task_id": "uuid-v4",
  "control_points": [
    {
      "pixel_x": 100.5,
      "pixel_y": 200.3,
      "geo_x": 116.3,
      "geo_y": 39.9
    }
  ],
  "target_crs": "EPSG:4326"
}
```

**字段说明:**
- `pixel_x`, `pixel_y`: 图像坐标（像素）
- `geo_x`, `geo_y`: 地理坐标（经度、纬度）
- `target_crs`: 目标坐标系（默认 WGS84）

**响应 (200):**
```json
{
  "status": "success",
  "task_id": "uuid-v4",
  "output_path": "outputs/uuid-v4_georeferenced.tiff",
  "rms_error": 0.00123,
  "gcp_count": 4
}
```

**错误响应 (400):**
```json
{
  "detail": "至少需要3个控制点"
}
```

---

### 4. 处理任务

#### 开始处理

```http
POST /api/processing/start
Content-Type: application/json
```

**请求体:**
```json
{
  "task_id": "uuid-v4",
  "auto_process": false,
  "enable_georeferencing": true
}
```

**字段说明:**
- `auto_process`: 是否跳过配准直接处理
- `enable_georeferencing`: 是否应用地理配准

**响应 (200):**
```json
{
  "message": "Processing task started",
  "task_id": "uuid-v4",
  "status": "started"
}
```

#### 获取处理状态

```http
GET /api/processing/status/{task_id}
```

**响应 (200):**
```json
{
  "task_id": "uuid-v4",
  "status": "processing",
  "progress": 0.6,
  "message": "Extracting contour lines...",
  "result": null,
  "error": null
}
```

#### 获取处理结果

```http
GET /api/processing/result/{task_id}
```

**响应 (200):**
```json
{
  "task_id": "uuid-v4",
  "status": "completed",
  "result_files": [
    "/api/files/uuid-v4/contours.geojson",
    "/api/files/uuid-v4/boundaries.geojson"
  ],
  "error": null
}
```

---

### 5. 文件下载

#### 下载结果（ZIP）

```http
GET /api/files/download/{task_id}
```

**响应:** ZIP 文件（`{task_id}_results.zip`）

#### 下载单个文件

```http
GET /api/files/{task_id}/{filename}
```

**响应:** 文件内容

**支持的文件类型:**
- `.geojson`: GeoJSON 格式
- `.shp`: Shapefile 格式
- `.tiff`: GeoTIFF 图像

#### 列出文件

```http
GET /api/files/list/{task_id}
```

**响应 (200):**
```json
{
  "task_id": "uuid-v4",
  "files": [
    {
      "filename": "contours.geojson",
      "url": "/api/files/uuid-v4/contours.geojson",
      "size": 12345
    }
  ]
}
```

---

### 6. WebSocket 实时进度

#### 连接 WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/{task_id}')

ws.onmessage = (event) => {
  const data = JSON.parse(event.data)

  if (data.type === 'progress') {
    console.log(`Progress: ${data.progress * 100}% - ${data.message}`)
  } else if (data.type === 'complete') {
    console.log('Complete:', data.result)
  } else if (data.type === 'error') {
    console.log('Error:', data.error)
  }
}
```

**消息类型:**

| 类型 | 字段 | 说明 |
|------|------|------|
| `progress` | `progress`, `message` | 进度更新 |
| `complete` | `result` | 处理完成 |
| `error` | `error` | 处理失败 |

---

## 错误处理

所有错误响应遵循以下格式：

```json
{
  "detail": "错误描述信息"
}
```

**HTTP 状态码:**
- `200`: 成功
- `400`: 请求错误（参数验证失败等）
- `404`: 资源未找到
- `500`: 服务器内部错误

---

## 示例代码

### JavaScript (前端)

```javascript
import axios from 'axios'

// 上传文件
async function uploadImage(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await axios.post('/api/upload/image', formData)
  return response.data
}

// 开始处理
async function startProcessing(taskId) {
  const response = await axios.post('/api/processing/start', {
    task_id: taskId,
    auto_process: true
  })
  return response.data
}

// 获取结果
async function getResults(taskId) {
  const response = await axios.get(`/api/processing/result/${taskId}`)
  return response.data
}
```

### Python

```python
import requests

# 上传文件
def upload_image(file_path):
    with open(file_path, 'rb') as f:
        files = {'file': f}
        response = requests.post('http://localhost:8000/api/upload/image', files=files)
    return response.json()

# 提交配准控制点
def submit_control_points(task_id, control_points):
    data = {
        'task_id': task_id,
        'control_points': control_points,
        'target_crs': 'EPSG:4326'
    }
    response = requests.post('http://localhost:8000/api/registration/submit', json=data)
    return response.json()

# 开始处理
def start_processing(task_id):
    data = {
        'task_id': task_id,
        'auto_process': True
    }
    response = requests.post('http://localhost:8000/api/processing/start', json=data)
    return response.json()

# 下载结果
def download_results(task_id, output_path):
    response = requests.get(f'http://localhost:8000/api/files/download/{task_id}')
    with open(output_path, 'wb') as f:
        f.write(response.content)
```

---

**版本**: 0.1.0
**最后更新**: 2026-03-04

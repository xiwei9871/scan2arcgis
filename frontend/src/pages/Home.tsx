import React, { useState } from 'react'
import { Card, Alert, Typography, Tag, Space, Modal, Table, Button, InputNumber, message } from 'antd'
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons'
import UploadComponent from '../components/Upload'
import { RegistrationCanvas } from '../components/RegistrationCanvas'
import { UploadResponse } from '../types'

const { Title, Text, Paragraph } = Typography

interface Point {
  x: number
  y: number
}

interface GeoPoint extends Point {
  latitude?: number
  longitude?: number
}

const Home: React.FC = () => {
  const [taskId, setTaskId] = useState<string>('')
  const [filename, setFilename] = useState<string>('')
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle')
  const [imageUrl, setImageUrl] = useState<string>('')
  const [controlPoints, setControlPoints] = useState<Point[]>([])
  const [geoPoints, setGeoPoints] = useState<GeoPoint[]>([])
  const [registrationModalVisible, setRegistrationModalVisible] = useState<boolean>(false)

  // Handle successful upload
  const handleUploadSuccess = (response: UploadResponse) => {
    setTaskId(response.task_id)
    setFilename(response.filename)
    setUploadStatus('success')
    // Show registration modal after upload success
    setRegistrationModalVisible(true)
    // Set image URL (assuming the uploaded file is accessible via URL)
    setImageUrl(`/api/uploads/${response.filename}`)
  }

  // Handle upload error
  const handleUploadError = () => {
    setUploadStatus('error')
    setTaskId('')
    setFilename('')
  }

  // Handle control points change
  const handlePointsChange = (points: Point[]) => {
    setControlPoints(points)
    // Update geo points to match
    const newGeoPoints: GeoPoint[] = points.map((point, index) => {
      const existingGeoPoint = geoPoints[index]
      return {
        ...point,
        latitude: existingGeoPoint?.latitude,
        longitude: existingGeoPoint?.longitude,
      }
    })
    setGeoPoints(newGeoPoints)
  }

  // Handle geo coordinate change
  const handleGeoCoordinateChange = (index: number, field: 'latitude' | 'longitude', value: number | null) => {
    const newGeoPoints = [...geoPoints]
    newGeoPoints[index] = {
      ...newGeoPoints[index],
      [field]: value ?? undefined,
    }
    setGeoPoints(newGeoPoints)
  }

  // Handle registration submit
  const handleRegistrationSubmit = () => {
    if (controlPoints.length < 3) {
      message.error('请至少标记 3 个控制点')
      return
    }

    const missingCoordinates = geoPoints.some(
      (point) => point.latitude === undefined || point.longitude === undefined
    )
    if (missingCoordinates) {
      message.error('请为所有控制点输入地理坐标')
      return
    }

    console.log('Registration data:', {
      taskId,
      controlPoints,
      geoPoints,
    })

    message.success('地理配准数据已提交')
    setRegistrationModalVisible(false)

    // TODO: Send registration data to backend
  }

  return (
    <div style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ marginBottom: '2rem' }}>
        <Title level={2}>Geological Map Digitizer</Title>
        <Paragraph style={{ color: '#666', fontSize: '16px' }}>
          Upload and digitize geological maps with AI-powered feature extraction
        </Paragraph>
      </div>

      <UploadComponent
        onUploadSuccess={handleUploadSuccess}
        onUploadError={handleUploadError}
      />

      {/* Display upload success information */}
      {uploadStatus === 'success' && taskId && (
        <Card
          style={{ marginTop: '1rem' }}
          title={
            <Space>
              <CheckCircleOutlined style={{ color: '#52c41a' }} />
              <span>Upload Successful</span>
            </Space>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="middle">
            <div>
              <Text strong>Task ID:</Text>
              <br />
              <Text code>{taskId}</Text>
            </div>

            <div>
              <Text strong>Filename:</Text>
              <br />
              <Text>{filename}</Text>
            </div>

            <div>
              <Text strong>Status:</Text>
              <br />
              <Tag color="blue" icon={<LoadingOutlined />}>
                Processing
              </Tag>
            </div>

            <Alert
              message="Your file is being processed"
              description="The geological map is being analyzed. You can track the progress using the task ID."
              type="info"
              showIcon
            />
          </Space>
        </Card>
      )}

      {/* Display upload error */}
      {uploadStatus === 'error' && (
        <Alert
          message="Upload Failed"
          description="There was an error uploading your file. Please try again."
          type="error"
          showIcon
          style={{ marginTop: '1rem' }}
        />
      )}

      {/* Registration Modal */}
      <Modal
        title="地理配准 - 标记控制点"
        open={registrationModalVisible}
        onCancel={() => setRegistrationModalVisible(false)}
        width={1200}
        footer={[
          <Button key="cancel" onClick={() => setRegistrationModalVisible(false)}>
            取消
          </Button>,
          <Button
            key="submit"
            type="primary"
            onClick={handleRegistrationSubmit}
            disabled={controlPoints.length < 3}
          >
            提交配准
          </Button>,
        ]}
      >
        <div style={{ height: '600px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, marginBottom: '1rem' }}>
            <RegistrationCanvas imageUrl={imageUrl} onPointsChange={handlePointsChange} />
          </div>

          {/* Geo coordinates table */}
          <div style={{ marginTop: '1rem' }}>
            <Title level={5}>控制点地理坐标</Title>
            <Table
              dataSource={geoPoints.map((point, index) => ({ ...point, key: index }))}
              columns={[
                {
                  title: '序号',
                  dataIndex: 'key',
                  key: 'key',
                  width: 80,
                  render: (index: number) => index + 1,
                },
                {
                  title: '图像坐标 X',
                  dataIndex: 'x',
                  key: 'x',
                  width: 100,
                  render: (value: number) => value.toFixed(2),
                },
                {
                  title: '图像坐标 Y',
                  dataIndex: 'y',
                  key: 'y',
                  width: 100,
                  render: (value: number) => value.toFixed(2),
                },
                {
                  title: '纬度',
                  dataIndex: 'latitude',
                  key: 'latitude',
                  width: 150,
                  render: (value: number | undefined, record: any) => (
                    <InputNumber
                      value={value}
                      onChange={(val) =>
                        handleGeoCoordinateChange(record.key, 'latitude', val)
                      }
                      placeholder="输入纬度"
                      style={{ width: '100%' }}
                    />
                  ),
                },
                {
                  title: '经度',
                  dataIndex: 'longitude',
                  key: 'longitude',
                  width: 150,
                  render: (value: number | undefined, record: any) => (
                    <InputNumber
                      value={value}
                      onChange={(val) =>
                        handleGeoCoordinateChange(record.key, 'longitude', val)
                      }
                      placeholder="输入经度"
                      style={{ width: '100%' }}
                    />
                  ),
                },
              ]}
              pagination={false}
              size="small"
            />
            {controlPoints.length > 0 && controlPoints.length < 3 && (
              <Alert
                message="至少需要标记 3 个控制点才能进行地理配准"
                type="warning"
                showIcon
                style={{ marginTop: '1rem' }}
              />
            )}
          </div>
        </div>
      </Modal>
    </div>
  )
}

export default Home

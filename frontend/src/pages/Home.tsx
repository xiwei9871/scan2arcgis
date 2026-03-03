import React, { useState } from 'react'
import { Card, Alert, Typography, Tag, Space } from 'antd'
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons'
import UploadComponent from '../components/Upload'
import { UploadResponse } from '../types'

const { Title, Text, Paragraph } = Typography

const Home: React.FC = () => {
  const [taskId, setTaskId] = useState<string>('')
  const [filename, setFilename] = useState<string>('')
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'success' | 'error'>('idle')

  // Handle successful upload
  const handleUploadSuccess = (response: UploadResponse) => {
    setTaskId(response.task_id)
    setFilename(response.filename)
    setUploadStatus('success')
  }

  // Handle upload error
  const handleUploadError = () => {
    setUploadStatus('error')
    setTaskId('')
    setFilename('')
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
    </div>
  )
}

export default Home

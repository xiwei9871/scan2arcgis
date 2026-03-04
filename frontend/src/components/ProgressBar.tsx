import { Progress, Card, Typography, Button, Space } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'

const { Text } = Typography

interface ProgressBarProps {
  progress: number
  message: string
  error?: string | null
  isConnected?: boolean
  onReconnect?: () => void
}

function ProgressBar({
  progress,
  message,
  error,
  isConnected = true,
  onReconnect
}: ProgressBarProps) {

  const getStatus = () => {
    if (error) return 'exception'
    if (progress === 100) return 'success'
    return 'active'
  }

  const getStatusText = () => {
    if (error) return 'Error'
    if (progress === 100) return 'Completed'
    return 'Processing...'
  }

  return (
    <Card
      title={
        <Space>
          <span>Processing Progress</span>
          <Text type="secondary">({getStatusText()})</Text>
        </Space>
      }
      style={{ marginTop: '20px' }}
      extra={
        !isConnected && onReconnect && progress < 100 && (
          <Button
            icon={<ReloadOutlined />}
            size="small"
            onClick={onReconnect}
          >
            Reconnect
          </Button>
        )
      }
    >
        <Progress
          percent={Math.round(progress)}
          status={getStatus()}
          strokeColor={{
            '0%': '#108ee9',
            '100%': '#87d068',
          }}
        />
        <div style={{ marginTop: '12px' }}>
          <Text type="secondary">{message}</Text>
          {error && (
            <Text type="danger" style={{ marginLeft: '12px' }}>
              - {error}
            </Text>
          )}
        </div>
        {!isConnected && progress < 100 && !error && (
          <Text type="warning" style={{ fontSize: '12px', marginTop: '8px', display: 'block' }}>
            Connection lost - attempting to reconnect...
          </Text>
        )}
      </Card>
  )
}

export default ProgressBar

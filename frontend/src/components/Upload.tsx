import React, { useState } from 'react'
import { Upload, message } from 'antd'
import { InboxOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import { uploadImage } from '../services/api'
import { UploadResponse } from '../types'

const { Dragger } = Upload

interface UploadComponentProps {
  onUploadSuccess: (response: UploadResponse) => void
  onUploadError?: (error: string) => void
}

const UploadComponent: React.FC<UploadComponentProps> = ({
  onUploadSuccess,
  onUploadError,
}) => {
  const [uploading, setUploading] = useState(false)
  const [fileList, setFileList] = useState<any[]>([])

  // Validate file type
  const beforeUpload = (file: File) => {
    const isValidType =
      file.type === 'image/png' ||
      file.type === 'image/jpeg' ||
      file.type === 'image/jpg' ||
      file.type === 'application/pdf'

    if (!isValidType) {
      message.error('You can only upload PNG, JPG, or PDF files!')
      return Upload.LIST_IGNORE
    }

    // Validate file size (max 10MB)
    const isLt10M = file.size / 1024 / 1024 < 10
    if (!isLt10M) {
      message.error('File must be smaller than 10MB!')
      return Upload.LIST_IGNORE
    }

    return false // Prevent automatic upload
  }

  // Handle file upload
  const handleUpload = async (file: File) => {
    try {
      setUploading(true)
      message.loading({ content: 'Uploading file...', key: 'upload', duration: 0 })

      const response = await uploadImage(file)

      message.success({ content: 'File uploaded successfully!', key: 'upload', duration: 2 })

      // Call success callback
      onUploadSuccess(response)

      // Clear file list
      setFileList([])
    } catch (error: any) {
      console.error('Upload error:', error)

      const errorMessage =
        error.response?.data?.detail ||
        error.message ||
        'Failed to upload file. Please try again.'

      message.error({ content: errorMessage, key: 'upload', duration: 3 })

      // Call error callback if provided
      if (onUploadError) {
        onUploadError(errorMessage)
      }
    } finally {
      setUploading(false)
    }
  }

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: false,
    fileList,
    beforeUpload,
    customRequest: ({ file, onSuccess, onError }) => {
      handleUpload(file as File)
        .then(() => onSuccess?.('ok'))
        .catch((err) => onError?.(err))
    },
    onChange(info) {
      setFileList(info.fileList)
    },
    onRemove() {
      setFileList([])
    },
    disabled: uploading,
    accept: '.png,.jpg,.jpeg,.pdf',
  }

  return (
    <div style={{ marginBottom: '2rem' }}>
      <Dragger {...uploadProps}>
        <p className="ant-upload-drag-icon">
          <InboxOutlined style={{ fontSize: '48px', color: '#1890ff' }} />
        </p>
        <p className="ant-upload-text">
          Click or drag geological map file to this area to upload
        </p>
        <p className="ant-upload-hint">
          Support for PNG, JPG, or PDF files. Maximum file size is 10MB.
        </p>
      </Dragger>
    </div>
  )
}

export default UploadComponent

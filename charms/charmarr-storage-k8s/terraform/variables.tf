variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "charmarr-storage"
}

variable "channel" {
  description = "Channel that the charm is deployed from"
  type        = string
  default     = "latest/edge"
}

variable "config" {
  description = "Additional charm configuration options not covered by explicit variables"
  type        = map(string)
  default     = {}
}

variable "constraints" {
  description = "String listing constraints for this application"
  type        = string
  default     = "arch=amd64"
}

variable "model" {
  description = "Name of the model to deploy to"
  type        = string
}

variable "revision" {
  description = "Revision number of the charm"
  type        = number
  default     = null
}

variable "backend_type" {
  description = "Storage backend type: 'storage-class' or 'native-nfs'"
  type        = string

  validation {
    condition     = contains(["storage-class", "native-nfs"], var.backend_type)
    error_message = "backend_type must be 'storage-class' or 'native-nfs'"
  }
}

variable "storage_class" {
  description = "Kubernetes StorageClass name (required for backend_type=storage-class)"
  type        = string
  default     = ""
}

variable "size" {
  description = "Storage size to provision (e.g., 100Gi, 1Ti)"
  type        = string
  default     = "100Gi"
}

variable "nfs_server" {
  description = "NFS server IP or hostname (required for backend_type=native-nfs)"
  type        = string
  default     = ""
}

variable "nfs_path" {
  description = "NFS export path (required for backend_type=native-nfs)"
  type        = string
  default     = ""
}

variable "access_mode" {
  description = "PVC access mode: 'ReadWriteMany' or 'ReadWriteOnce'"
  type        = string
  default     = "ReadWriteMany"

  validation {
    condition     = contains(["ReadWriteMany", "ReadWriteOnce"], var.access_mode)
    error_message = "access_mode must be 'ReadWriteMany' or 'ReadWriteOnce'"
  }
}

variable "puid" {
  description = "User ID for file ownership"
  type        = number
  default     = 1000
}

variable "pgid" {
  description = "Group ID for file ownership"
  type        = number
  default     = 1000
}

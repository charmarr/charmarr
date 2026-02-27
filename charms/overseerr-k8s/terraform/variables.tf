variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "overseerr"
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

variable "owner" {
  description = "Owner of the Juju model"
  type        = string
  default     = "admin"
}

variable "revision" {
  description = "Revision number of the charm"
  type        = number
  default     = null
}

variable "ingress_port" {
  description = "Port for the Istio ingress gateway listener"
  type        = number
  default     = 80
}

variable "log_level" {
  description = "Application log level (debug, info, warn, error)"
  type        = string
  default     = "info"

  validation {
    condition     = contains(["debug", "info", "warn", "error"], var.log_level)
    error_message = "log_level must be one of: debug, info, warn, error"
  }
}

variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "flaresolverr"
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

variable "log_level" {
  description = "Log level for FlareSolverr (debug, info, warning, error)"
  type        = string
  default     = "info"

  validation {
    condition     = contains(["debug", "info", "warning", "error"], var.log_level)
    error_message = "log_level must be one of: debug, info, warning, error"
  }
}

variable "timeout" {
  description = "Maximum timeout in milliseconds for browser navigation"
  type        = number
  default     = 60000
}

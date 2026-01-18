variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "prowlarr"
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
  description = "Application log level (trace, debug, info, warn, error)"
  type        = string
  default     = "info"

  validation {
    condition     = contains(["trace", "debug", "info", "warn", "error"], var.log_level)
    error_message = "log_level must be one of: trace, debug, info, warn, error"
  }
}

variable "ingress_path" {
  description = "URL path prefix for ingress routing"
  type        = string
  default     = "/prowlarr"

  validation {
    condition     = length(var.ingress_path) > 0 && substr(var.ingress_path, 0, 1) == "/"
    error_message = "ingress_path must start with /"
  }
}

variable "timezone" {
  description = "IANA timezone (e.g., America/New_York, Europe/London)"
  type        = string
  default     = "Etc/UTC"
}

variable "sync_level" {
  description = "Sync level for connected applications (full-sync, add-remove-only, disabled)"
  type        = string
  default     = "full-sync"

  validation {
    condition     = contains(["full-sync", "add-remove-only", "disabled"], var.sync_level)
    error_message = "sync_level must be one of: full-sync, add-remove-only, disabled"
  }
}

variable "api_key_rotation" {
  description = "Auto-rotate API key schedule (disabled, daily, monthly, yearly)"
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "daily", "monthly", "yearly"], var.api_key_rotation)
    error_message = "api_key_rotation must be one of: disabled, daily, monthly, yearly"
  }
}

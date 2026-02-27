variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "radarr"
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

variable "variant" {
  description = "Content variant: standard (default), 4k (UHD), or anime"
  type        = string
  default     = "standard"

  validation {
    condition     = contains(["standard", "4k", "anime"], var.variant)
    error_message = "variant must be one of: standard, 4k, anime"
  }
}

variable "trash_profiles" {
  description = "Comma-separated list of Trash Guide profile templates to sync via Recyclarr (e.g., hd-bluray-web)"
  type        = string
  default     = ""
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

variable "ingress_port" {
  description = "Port for the Istio ingress gateway listener"
  type        = number
  default     = 80
}

variable "ingress_path" {
  description = "URL path prefix for ingress routing"
  type        = string
  default     = "/radarr"

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

variable "api_key_rotation" {
  description = "Auto-rotate API key schedule (disabled, daily, monthly, yearly)"
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "daily", "monthly", "yearly"], var.api_key_rotation)
    error_message = "api_key_rotation must be one of: disabled, daily, monthly, yearly"
  }
}

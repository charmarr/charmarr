variable "app_name" {
  description = "Name to give the deployed application"
  type        = string
  default     = "plex"
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

variable "claim_token" {
  description = "Plex claim token for automated server setup (get from https://plex.tv/claim)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "hardware_transcoding" {
  description = "Enable hardware transcoding using Intel QuickSync (requires /dev/dri and Plex Pass)"
  type        = bool
  default     = false
}

variable "timezone" {
  description = "IANA timezone (e.g., America/New_York, Europe/London)"
  type        = string
  default     = "Etc/UTC"
}

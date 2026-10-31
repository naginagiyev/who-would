variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "austriaeast"
}

variable "ssh_source_ip" {
  type = string
}

variable "vm_size" {
  type    = string
  default = "Standard_B2ats_v2"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/who-would.pub"
}

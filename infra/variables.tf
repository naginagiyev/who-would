variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "austriaeast"
}

variable "ssh_source_ips" {
  type = list(string)
}

variable "vm_size" {
  type    = string
  default = "Standard_B2ats_v2"
}

variable "ssh_public_key_path" {
  type    = string
  default = "~/.ssh/who-would.pub"
}

variable "github_repo" {
  type    = string
  default = "naginagiyev@148803359/who-would@1429557749"
}

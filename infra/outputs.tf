output "public_ip" {
  value = azurerm_public_ip.main.ip_address
}

output "azure_client_id" {
  value = azurerm_user_assigned_identity.deploy.client_id
}

output "azure_tenant_id" {
  value = azurerm_user_assigned_identity.deploy.tenant_id
}

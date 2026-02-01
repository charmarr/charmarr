data "juju_model" "model" {
  name  = var.model
  owner = var.owner
}

resource "juju_application" "gluetun" {
  name       = var.app_name
  model_uuid = data.juju_model.model.uuid
  trust      = true

  charm {
    name     = "gluetun-k8s"
    channel  = var.channel
    revision = var.revision
  }

  constraints = var.constraints

  config = merge(
    {
      cluster-cidrs       = var.cluster_cidrs
      vpn-provider        = var.vpn_provider
      vpn-type            = var.vpn_type
      wireguard-addresses = var.wireguard_addresses
      # FIXME: Uncomment once https://github.com/juju/juju/issues/20143 is fixed
      # wireguard-private-key-secret = var.wireguard_private_key_secret
      server-countries     = var.server_countries
      server-cities        = var.server_cities
      vpn-endpoint-ip      = var.vpn_endpoint_ip
      vpn-endpoint-port    = tostring(var.vpn_endpoint_port)
      wireguard-public-key = var.wireguard_public_key
      vxlan-id             = tostring(var.vxlan_id)
      dns-over-tls         = tostring(var.dns_over_tls)
    },
    var.config
  )
}

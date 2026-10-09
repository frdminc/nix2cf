# The same Site Model as services.yml, written as a Nix expression.
#
# This is the "Nix-expressed input" path in its smallest honest form: a plain
# attribute set that `nix-instantiate --eval --strict --json` turns into the
# JSON the compiler consumes (`nix2cf eval-nix examples/site/site.nix`). No
# nixpkgs, no `lib`, no module system: the D12 frontend (mkOption / mkIf /
# mkDefault, paper §2.6's illustrative edge-http.nix) is NOT built, and the
# name nix2cf is historical — YAML/JSON stays the wire format and the path a
# stranger uses (guide §3). tests/test_compile.py evaluates this file when a
# Nix install is present and checks it equals services.yml; it is skipped
# otherwise.
#
# FIXTURE, not site data (D21).
{
  contract_version = 1;

  domains = {
    macos-launchd-services = {
      description = "launchd jobs on the operator's Mac under com.djbclark.* and org.tendcf.*";
    };
    macos-user-daemons = {
      description = "Third-party login items and vendor updaters";
      comprehensive = false;
      opt_out_reason = "deliberately-unmanaged";
      note = "Another tool's territory. Permanent, and this is the rare case.";
    };
    android-termux-services = {
      description = "Termux/tendcf-agent services on the fleet devices";
      comprehensive = false;
      opt_out_reason = "not-yet-migrated";
      note = "Transcribed at Step 2. This count is the backlog.";
    };
  };

  bundles = {
    edge-http = {
      description = "Public HTTP edge: nothing in it is modified unless the whole bundle re-verifies";
      domain = "macos-launchd-services";
    };
    fleet-vpn = {
      description = "VPN transport and the lockdown policy that depends on it";
      domain = "macos-launchd-services";
      interlocks = [
        {
          id = "tailscale-authenticated-before-lockdown";
          description = "The mesh VPN must be authenticated before always-on VPN lockdown may be enforced. Setting lockdown on a device whose VPN is unauthenticated severs every management path to it.";
          pre_action = {
            command = [ "tailscale" "status" "--json" ];
            expect_exit = 0;
            timeout_seconds = 15;
          };
          defines_class = "tailscale_authenticated";
          blocks = "enclosing-bundle";
          report = true;
        }
      ];
    };
  };

  services = [
    {
      name = "caddy";
      description = "Site reverse proxy and HTTPS terminator";
      domain = "macos-launchd-services";
      bundle = "edge-http";
      platform = "macos";
      hosts = [ "mac" ];
      runs_as = "djbclark";
      command = [ "/opt/homebrew/bin/caddy" "run" "--config" "/etc/caddy/Caddyfile" ];
      managed_by = "cfengine";
      launchd = {
        label = "com.djbclark.caddy";
        run_at_load = true;
        keep_alive = true;
      };
      provides = [ "service:caddy" "port:443" "port:80" ];
      requires = [ "path:/etc/caddy/Caddyfile" "service:tailscaled" ];
      platform_notes = "Port allocations are site-private authorities, existence-checked at compile time.";
    }
    {
      name = "litellm-proxy";
      description = "LLM gateway behind Caddy";
      domain = "macos-launchd-services";
      bundle = "edge-http";
      platform = "macos";
      role = "llm-gateway";
      runs_as = "djbclark";
      command = [ "/opt/homebrew/bin/litellm" "--config" "/etc/litellm/config.yaml" ];
      env = {
        LITELLM_MASTER_KEY = "LITELLM_MASTER_KEY";
        OPENAI_API_KEY = "OPENAI_API_KEY";
      };
      managed_by = "cfengine";
      launchd = { label = "com.djbclark.litellm"; };
      provides = [ "service:litellm" "port:4000" ];
      requires = [ "service:caddy" "secret:LITELLM_MASTER_KEY" ];
    }
    {
      name = "tailscaled";
      description = "Mesh VPN transport";
      domain = "macos-launchd-services";
      bundle = "fleet-vpn";
      platform = "macos";
      hosts = [ "mac" ];
      runs_as = "root";
      command = [ "/usr/local/bin/tailscaled" ];
      managed_by = "cfengine";
      launchd = { label = "org.tendcf.tailscaled"; };
      provides = [ "service:tailscaled" "network:tailnet" ];
    }
  ];
}

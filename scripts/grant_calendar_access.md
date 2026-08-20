# One-time admin setup: calendar access for the deadline sync

The Outlook sync needs the Graph **application** permission
`Calendars.ReadWrite`. Unlike `Sites.Selected`, this permission has no
built-in per-resource scoping: once consented, the app token can touch
**every mailbox in the tenant**. The deployment answer is an Exchange
**ApplicationAccessPolicy** that restricts the app to a named group of
mailboxes — the calendar-side equivalent of the site grant recorded in
`grant_site_access.md`. Do both steps; consent without the policy is not
an acceptable end state outside a throwaway tenant.

## 1. Add the permission (Entra admin center)

1. Entra admin center → **App registrations** → the agent's registration
   → **API permissions**.
2. **Add a permission** → Microsoft Graph → **Application permissions** →
   `Calendars.ReadWrite`.
3. **Grant admin consent** for the tenant.

## 2. Scope it with an ApplicationAccessPolicy (Exchange Online PowerShell)

Requires the ExchangeOnlineManagement module and an Exchange admin:

```powershell
Install-Module ExchangeOnlineManagement   # once
Connect-ExchangeOnline

# A mail-enabled security group holding the mailboxes the app may touch.
New-DistributionGroup -Name "Deadline Agent Mailboxes" `
    -Alias deadline-agent-mailboxes -Type Security
Add-DistributionGroupMember -Identity deadline-agent-mailboxes `
    -Member pat@yourtenant.onmicrosoft.com

# Deny the app every mailbox outside the group.
New-ApplicationAccessPolicy -AppId <GRAPH_CLIENT_ID> `
    -PolicyScopeGroupId deadline-agent-mailboxes@yourtenant.onmicrosoft.com `
    -AccessRight RestrictAccess `
    -Description "contract-deadline-agent: calendar sync mailboxes only"
```

## 3. Verify the blast radius

```powershell
# Expect AccessCheckResult: Granted
Test-ApplicationAccessPolicy -AppId <GRAPH_CLIENT_ID> `
    -Identity pat@yourtenant.onmicrosoft.com

# Expect AccessCheckResult: Denied — this is the point of the exercise
Test-ApplicationAccessPolicy -AppId <GRAPH_CLIENT_ID> `
    -Identity someone-else@yourtenant.onmicrosoft.com
```

The policy can take up to ~30 minutes to start enforcing. Note the same
asymmetry as the site grant: the admin uses powerful tooling once; the
app itself keeps the narrowest scope Exchange can express.

Newer tenants can use Exchange's **RBAC for Applications** instead
(role assignments with management scopes), which supersedes
ApplicationAccessPolicy; the policy above is the widely available
baseline and is sufficient here.

## 4. Configure the sync target

In `.env` (gitignored, like every credential here):

```
GRAPH_CALENDAR_USER=pat@yourtenant.onmicrosoft.com
```

The sync only ever addresses this one mailbox; the policy guarantees the
token could not do otherwise.

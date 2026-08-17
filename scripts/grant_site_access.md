# One-time admin grant: give the app access to the demo site

The app registration holds the Graph application permission `Sites.Selected`.
That permission is deliberately inert on its own: the app can reach **no**
SharePoint site until a tenant admin grants it access to a specific one. This
is the blast-radius design recorded in `docs/ARCHITECTURE.md` — a leaked app
credential exposes one granted site, not the tenant.

The grant itself must be made by an admin, with admin credentials — the app
cannot grant itself access. Easiest path is Graph Explorer, signed in as the
tenant admin.

## Steps (Graph Explorer)

1. Open https://developer.microsoft.com/graph/graph-explorer and sign in as
   the tenant admin.

2. **Resolve the site id.** Run:

   ```
   GET https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{site-path}
   ```

   e.g. `.../sites/contoso.sharepoint.com:/sites/Demos`. Copy the `id` from
   the response (a three-part value: hostname,guid,guid).

   If this returns 403, click **Modify permissions** in Graph Explorer and
   consent to `Sites.Read.All` (delegated) for this call.

3. **Grant the app write access to that site.** Run:

   ```
   POST https://graph.microsoft.com/v1.0/sites/{site-id}/permissions
   ```

   with request body (substitute your app's client id and display name):

   ```json
   {
     "roles": ["write"],
     "grantedToIdentities": [
       {
         "application": {
           "id": "<GRAPH_CLIENT_ID>",
           "displayName": "contract-deadline-agent"
         }
       }
     ]
   }
   ```

   This call needs the delegated `Sites.FullControl.All` permission in Graph
   Explorer — consent via **Modify permissions** if prompted. Note the
   asymmetry: the *admin's one-time grant* uses a powerful delegated
   permission; the *app* keeps only `Sites.Selected`. That is the point.

4. **Verify** with the app's own credentials:

   ```
   python scripts/provision_list.py
   ```

   If the site resolves and the library/list provision, the grant worked.
   A 403 means the grant has not applied (or targeted the wrong site).

## Notes

- `roles: ["write"]` is enough to create lists, columns, items, and upload
  files. Do not grant `fullcontrol` — the pipeline does not need it.
- To revoke: `GET /sites/{site-id}/permissions` to find the permission id,
  then `DELETE /sites/{site-id}/permissions/{permission-id}`.
- Repeat step 3 per additional site if the app should ever reach more than
  one; each grant is explicit and auditable.

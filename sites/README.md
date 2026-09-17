# Leader guide sites

Two self-contained static pages, each deployable as its own Netlify project.

| Folder | Page | Netlify project | Target URL |
| --- | --- | --- | --- |
| `pcguide/` | Pastoral Care Guide | `pcguide-celebration` | `pcguide.celebrationpeople.church` |
| `nsresource/` | Next Steps Resource | `nsresource-celebration` | `nsresource.celebrationpeople.church` |

Each folder serves its page at **both** the site root and its named path, so
`<site>.netlify.app` and `<site>.netlify.app/pcguide` both work. Nothing needs a
build step — the publish directory is the folder itself.

## Deploying

Drag the folder onto the Deploys tab of the matching Netlify project, or link
the project to this repo with the publish directory set to `sites/pcguide` or
`sites/nsresource` and the build command left empty.

## Attaching the subdomains

`celebrationpeople.church` is served by NS1 nameservers (`dns1.p03.nsone.net`
and friends), which is **Netlify DNS**. Netlify therefore manages the zone
itself: adding the subdomain to a project creates the DNS record and provisions
the Let's Encrypt certificate automatically. There is nothing to change at the
registrar.

For each project: **Domain management → Add a domain alias**, then enter
`pcguide.celebrationpeople.church` or `nsresource.celebrationpeople.church`.

Neither subdomain resolves yet, so no existing record gets overwritten.

## Note on the apex domain

The apex `celebrationpeople.church` currently resolves to `98.84.224.111` and
`18.208.88.157` — AWS addresses, not Netlify — even though the `legacy-cc`
project lists the domain as its primary URL. Those A records live in the
Netlify DNS zone but point elsewhere. Adding the two subdomains does not touch
them, and `legacy-cc` is left alone.

# Leader guide sites

Two self-contained static pages, each deployable as its own Netlify site.

| Folder | Page | Intended URL |
| --- | --- | --- |
| `pcguide/` | Pastoral Care Guide | `celebrationpeople.church/pcguide` |
| `nsresource/` | Next Steps Resource | `celebrationpeople.church/nsresource` |

Each folder serves its page at **both** the site root and its named path, so
`<site>.netlify.app` and `<site>.netlify.app/pcguide` both work. Nothing needs a
build step — publish directory is the folder itself.

## Deploying

Drag the folder onto the Deploys tab of the matching Netlify project, or point a
Git-linked project at this repo with the publish directory set to
`sites/pcguide` or `sites/nsresource`.

## Serving both under celebrationpeople.church

`celebrationpeople.church` resolves to a single Netlify project (`legacy-cc`).
A custom domain attaches to one project only, so the two guides cannot claim
paths on that domain by themselves. To keep them as separate projects and still
expose both paths, add these proxy rewrites to the **`legacy-cc`** `_redirects`
file (rewrites, status 200 — the visitor's URL stays on the church domain):

    /pcguide      https://<pcguide-site>.netlify.app/pcguide/            200
    /pcguide/*    https://<pcguide-site>.netlify.app/pcguide/:splat      200
    /nsresource   https://<nsresource-site>.netlify.app/nsresource/      200
    /nsresource/* https://<nsresource-site>.netlify.app/nsresource/:splat 200

Paths are case-sensitive, so `/Pcguide` will not match `/pcguide`. Add a
redirect if the capitalised form needs to work too:

    /Pcguide      /pcguide   301

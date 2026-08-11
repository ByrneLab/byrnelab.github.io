# Byrne Lab website

Static site for **byrnelab.science**, built with [Jekyll](https://jekyllrb.com/)
and hosted free on GitHub Pages. Replaces the Squarespace site.

Content lives in `_data/*.yml` — you can add a lab member or a paper without
touching any HTML.

---

## Before you start: two things to do in order

### 1. Do NOT cancel Squarespace yet

Keep the Squarespace subscription running until the new site is live and the
domain has moved. If you cancel first, the site goes dark and — depending on how
the domain is held — you can make the domain much harder to recover.

### 2. Check where `byrnelab.science` is registered

This matters more than the hosting. Run:

```bash
whois byrnelab.science | grep -i -E 'registrar|expiry|expiration'
```

- **If the registrar is Squarespace** (they acquired Google Domains, so this is
  likely): the domain is bundled with the subscription you're cancelling. You
  must **transfer it out to an independent registrar first** — Cloudflare
  Registrar and Namecheap are both fine and cost roughly $10–40/yr for a
  `.science` domain. Transfers require unlocking the domain and getting an auth
  code, and can take up to 5–7 days. Start this **before** cancelling.
- **If it's registered elsewhere** (Pitt IT, another registrar), you only need to
  change DNS records — much simpler.

A domain renewal is the one cost that does not go away by moving to GitHub
Pages. GitHub Pages hosting itself is $0.

---

## Repository setup

The repo is named `byrnelab.github.io` — GitHub treats `<name>.github.io` as a
root-level Pages site, so it serves at `https://byrnelab.github.io/` with no
subpath. That's why `baseurl` in `_config.yml` is empty.

The site is built by **GitHub Actions** (`.github/workflows/deploy.yml`) using
Jekyll 4 — not the legacy branch-based build, which pins Jekyll 3.9.

### Create the `byrnelab` organization first

The repo name `byrnelab.github.io` only produces a root-level site if the owner
is literally named `byrnelab`. `gh` cannot create organizations, so do this once
in the browser: **https://github.com/organizations/new** → Free plan → name it
`byrnelab`.

(If you'd rather skip the org and use your personal account, the repo must
instead be named `<your-username>.github.io`, and the DNS `CNAME` target below
changes to match.)

### First push

```bash
cd byrnelab

# Hold the custom domain back until DNS is ready — see the note below.
rm -f CNAME

# Stale lockfile from the earlier github-pages Gemfile, if present.
rm -f Gemfile.lock

git init
git add .
git commit -m "Initial Jekyll site migrated from Squarespace"
git branch -M main

gh repo create byrnelab/byrnelab.github.io \
  --public --source=. --remote=origin --push
```

The repo must be **public** — Pages on private repos requires a paid GitHub
plan.

### Enable Pages

**Settings → Pages → Build and deployment → Source: GitHub Actions.**

This is a one-time click and it is easy to miss. Until you set it, the workflow
runs and then fails at the deploy step.

Watch the run with `gh run watch`, or under the repo's Actions tab. First build
takes ~2 minutes. The site then appears at **https://byrnelab.github.io/**.

> **Check every page there before touching DNS.** Nothing is public-facing at
> this stage — the Squarespace site is still serving byrnelab.science.

### Why remove CNAME first

The `CNAME` file tells GitHub the site's custom domain. If it's present before
DNS points at GitHub, `byrnelab.github.io` redirects to `www.byrnelab.science`
— which still resolves to Squarespace — and you can't preview anything.

You don't need to restore the file by hand. When you set the custom domain in
**Settings → Pages** at cutover, GitHub commits a correct `CNAME` for you.

---

## Images

The image files are **not** in this repo — they still live on Squarespace's CDN,
which blocked automated download. `fetch_images.py` pulls all 38 of them and
optimizes them into the right folders. Run it on your own machine:

```bash
pip install pillow
python3 fetch_images.py
```

Expect `38/38 downloaded`. Then:

```bash
python3 verify_site.py     # should report 0 images missing
git add assets/images && git commit -m "Add images" && git push
```

If Squarespace is already cancelled by the time you run this, the URLs will 404.
**Run it while the old site is still up**, or substitute your own originals —
these are your lab's images and you'll have most at higher quality locally.

---

## Custom domain

Only after the `github.io` URL looks correct.

**At your DNS provider**, create:

| Type  | Name  | Value                                             |
|-------|-------|---------------------------------------------------|
| A     | `@`   | `185.199.108.153`                                 |
| A     | `@`   | `185.199.109.153`                                 |
| A     | `@`   | `185.199.110.153`                                 |
| A     | `@`   | `185.199.111.153`                                 |
| CNAME | `www` | `byrnelab.github.io`                              |

Remove the old Squarespace A/CNAME records for `@` and `www` at the same time.

> Verify these IPs against
> [GitHub's current documentation](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)
> before entering them — GitHub has changed them before.

**Then in GitHub:** Settings → Pages → Custom domain → enter
`www.byrnelab.science` → Save. Once the DNS check passes, tick
**Enforce HTTPS** (the certificate can take up to 24h to issue).

Setting the custom domain in Settings commits the `CNAME` file for you — you
deleted it before the first push so that the `github.io` preview would work.

DNS propagation takes anywhere from minutes to 48 hours. Check with:

```bash
dig +short www.byrnelab.science
```

---

## Editing the site

### Add a lab member

1. Put a square-ish photo in `assets/images/people/` named
   `firstname-lastname.jpg`.
2. Add to `_data/people.yml`:

   ```yaml
   - name: Jane Doe
     role: Postdoctoral fellow
     photo: jane-doe.jpg
     group: postdocs        # pi | postdocs | students | staff
   ```

Groups render as headings in this order: Principal Investigator, Postdoctoral
Fellows, Students, Staff. A typo in `group` won't lose anyone — they fall into
an "Other" section, and `verify_site.py` warns you.

> **Note:** the old site never listed Leah on the People page. The `pi` group is
> wired up and ready — add an entry with `group: pi` and it appears at the top.

### Add a publication

Add to the **top** of `_data/publications.yml` (newest first):

```yaml
- year: 2026
  authors: Byrne LC, Someone Else
  title: Title of the paper
  venue: Journal Name 12(3):45-67
  doi: https://doi.org/10.xxxx/xxxxx
  pubmed: https://pubmed.ncbi.nlm.nih.gov/xxxxxxxx/   # optional
  note: Preprint                                       # optional
```

Only `year`, `authors`, `title`, `venue` are required.

### Other edits

| What                      | Where                          |
|---------------------------|--------------------------------|
| Research areas            | `_data/projects.yml`           |
| Home page image mosaic    | `_data/gallery.yml`            |
| Job postings              | `join.html`                    |
| Address, social links     | `_config.yml`                  |
| Navigation menu           | `_config.yml` (`nav:`)         |
| Colors, fonts, spacing    | `assets/css/style.scss` (`:root`) |

Committing to `main` republishes automatically in about a minute. Small edits
can be made directly in GitHub's web editor — no local setup needed.

---

## Local preview (optional)

Docker — no Ruby needed, and now matches CI since both run Jekyll 4:

```bash
docker run --rm -p 4000:4000 \
  -v "$PWD":/srv/jekyll \
  -v jekyll-gems:/usr/local/bundle \
  jekyll/jekyll:4 sh -c "bundle install && jekyll serve --host 0.0.0.0"
```

The named `jekyll-gems` volume caches the gems, so only the first run is slow.

Or natively, if you have Ruby 3.x (`brew install ruby` — macOS system Ruby is
too old):

```bash
bundle install
bundle exec jekyll serve
```

Either way: http://localhost:4000. You don't need this to run the site — GitHub
builds it on every push — but it's useful for larger changes.

---

## Checking your work

```bash
python3 verify_site.py
```

Validates YAML, checks Liquid blocks are balanced and nested, confirms internal
links resolve, flags missing images and missing required fields. Exits non-zero
on error. Worth running before any push, especially after editing YAML — a bad
indent there is the single most likely way to break the build.

---

## What changed from Squarespace

- All seven pages carried over, same URLs (`/science/`, `/people/`,
  `/publications/`, `/join/`, `/contact/`, `/pgtb/`).
- Publications are structured data with DOI/PubMed links, grouped by year.
- Home mosaic now has a keyboard-accessible lightbox (arrow keys, Escape).
- Real alt text on images, skip-link, focus styles.
- Added a 404 page, `sitemap.xml`, and Open Graph tags.
- Dropped the unused Squarespace shopping-cart markup.

## Cost

| Item             | Before          | After         |
|------------------|-----------------|---------------|
| Hosting          | Squarespace fee | **$0**        |
| Domain           | included        | ~$10–40/yr    |
| TLS certificate  | included        | **$0**        |

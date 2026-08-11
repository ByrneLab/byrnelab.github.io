source "https://rubygems.org"

# Jekyll 4 directly, rather than the `github-pages` metapackage.
# The site is built by GitHub Actions (.github/workflows/deploy.yml), so we're
# not tied to the Jekyll 3.9 version that the legacy branch-based Pages build
# pins. Local preview and CI therefore run identical versions.
gem "jekyll", "~> 4.3"

group :jekyll_plugins do
  gem "jekyll-seo-tag", "~> 2.8"
  gem "jekyll-sitemap", "~> 1.4"
end

# Ruby 3.x no longer bundles a web server; jekyll serve needs this.
gem "webrick", "~> 1.8"

platforms :mingw, :x64_mingw, :mswin, :jruby do
  gem "tzinfo", ">= 1", "< 3"
  gem "tzinfo-data"
end

# Publish this folder to GitHub

From a machine where you are logged into GitHub:

```bash
cd odte-put-scanner   # or this directory
git init -b main
git add .
git commit -m "Initial 0DTE improved put-spread scanner"

# GitHub CLI
gh repo create odte-put-scanner --public --source=. --remote=origin --push

# or manual
# create an empty repo named odte-put-scanner on github.com, then:
git remote add origin git@github.com:YOUR_USER/odte-put-scanner.git
git push -u origin main
```

Do not commit live `chain.json` files with real quotes you do not want public.

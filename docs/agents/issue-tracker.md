# Issue tracker: GitHub

Issues for this repository live in GitHub Issues at MuZiJin701/zen-computer-marketplace. Use the gh CLI from the repository root; it resolves the repository from the Git remote.

GitHub Issues hold task and request tracking. Detailed development specifications live in docs/specs/ and should be referenced from their issue when published.

## Common operations

~~~powershell
gh issue list --state open --json number,title,body,labels,comments
gh issue view <number> --json number,title,body,labels,comments,state,url
gh issue create --title "..." --body-file <path>
gh issue edit <number> --body-file <path>
gh issue comment <number> --body-file <path>
gh issue edit <number> --add-label "..." --remove-label "..."
gh issue close <number>
~~~

Use appropriate state and label filters when listing issues. Read the body, labels and comments before updating an existing ticket. For multiline issue bodies or comments, save the exact text to a UTF-8 file and pass --body-file.

When a skill says to publish a ticket, create a GitHub issue. When it says to fetch a ticket, read the issue with its labels and comments. External writes follow the user's authorized task scope.

## Pull requests as a triage surface

**PRs as a request surface: no.**

Pull requests are not an incoming triage request surface for this repository. An explicitly requested PR review is still handled as a review.

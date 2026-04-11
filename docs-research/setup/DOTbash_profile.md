```
# Tab separated files
alias tawk="awk -F $'\t'"
alias tsort="sort -t $'\t'"
alias tjoin="join -t $'\t'"

# History
export HISTCONTROL=erasedups
export HISTSIZE="NOTHING"
export HISTFILESIZE="NOTHING"
shopt -s histappend
export PROMPT_COMMAND='history -a;echo'

# Quotes
cowsay -W 60 -b `shuf -n 1 ~/quotes`

# Bash Git Prompt
source $HOME/.bash-git-prompt/gitprompt.sh

gi () {
  curl -fL https://www.gitignore.io/api/${(j:,:)@}
}
```
#!/bin/bash

UTC() { date -u "+%Y%m%d-%H%M%S"; }

block_search () {
  find "$1" -type f -name "vasprun.xml*" > "$2"

  awk -F/ '{
    for (i = 1; i < NF; i++) {
      printf "%s", $i
      if ($i ~ /block/) {
        break
      }
      printf FS
    }
    print ""
    }' "$2" | sort | uniq -c > "$3"
}

generate_report() {
  backup=$(mktemp)
  re_org=$(mktemp)
  quar=$(mktemp)

  exec 3>"${backup}" 5>"${re_org}" 7>"${quar}"

  sep="===================================================================="

  printf "%s\nBLOCKS THAT CAN BE BACKED UP:\n" "${sep}" >&3
  printf "%s\nLAUNCHERS TO RE-ORG:\n" "${sep}" >&5
  printf "%s\nQUARANTINED LAUNCHERS FOUND, CHECK VALIDATION:\n" "${sep}" >&7

  local report="$1"
  shift
  local counts=("${@}")

  for file in "${counts[@]}"; do
    awk '/block/ { print $0 }' "${file}" >&3
    awk '!/block/ { print $0 }' "${file}" >&5
    awk '/quarantine/ { print $0 }' "${file}" >&7
  done

  cat "${backup}" "${re_org}" "${quar}" >> "${report}"

  rm "${backup}" "${re_org}" "${quar}"
  exec 3>&- 5>&- 7>&-
}

dir=$(pwd)

while getopts 'd:f:v' flag; do
  case "${flag}" in
    d) dir="${OPTARG}" ;;
    *) echo "Unexpected option ${flag}" ;;
  esac
done

IFS=$'\n'
dirs=($(find "${dir}" -maxdepth 1 -mindepth 1 -type d -not -path "${dir}/.emmet"))
unset IFS

search_logs=()
counts=()

for i in "${dirs[@]}"; do
  mkdir -p "${i}/.emmet"
  emmet="${i}/.emmet"
  search_logs+=("${emmet}/emmet-launcher-search-$(UTC).txt")
  counts+=("${emmet}/emmet-launcher-counts-$(UTC).txt")
done

export -f block_search

parallel --link block_search ::: "${dirs[@]}" ::: "${search_logs[@]}" ::: "${counts[@]}"

mkdir -p "${dir}/.emmet"
report_file="${dir}/.emmet/emmet-laucher-report-$(UTC).txt"

generate_report "${report_file}" "${counts[@]}"

import { useEffect, useMemo, useReducer, useRef } from "react"

interface SelectionState {
  key: string
  paths: string[]
}

type SelectionAction =
  | { type: "replace"; key: string; paths: Iterable<string>; checked: boolean }
  | { type: "reset"; key: string }

function updatePathSet(
  currentPaths: string[],
  affectedPaths: Iterable<string>,
  checked: boolean,
): string[] {
  const nextPaths = new Set(currentPaths)
  for (const path of affectedPaths) {
    if (checked) nextPaths.add(path)
    else nextPaths.delete(path)
  }
  return [...nextPaths]
}

function selectionReducer(
  state: SelectionState,
  action: SelectionAction,
): SelectionState {
  if (action.type === "reset") {
    return { key: action.key, paths: [] }
  }

  return {
    key: action.key,
    paths: updatePathSet(state.paths, action.paths, action.checked),
  }
}

interface CandidateSelection {
  selectedPaths: string[]
  selectedSet: Set<string>
  updatePath: (path: string, checked: boolean) => void
  updatePaths: (paths: Iterable<string>, checked: boolean) => void
  reset: () => void
}

/** Own destructive candidate selection for one exact scan-result signature. */
export function useCandidateSelection(
  selectionKey: string,
  isScanning: boolean,
): CandidateSelection {
  const [state, dispatch] = useReducer(selectionReducer, {
    key: selectionKey,
    paths: [],
  })
  const wasScanning = useRef(isScanning)

  if (state.key !== selectionKey) {
    dispatch({ type: "reset", key: selectionKey })
  }

  useEffect(() => {
    if (isScanning && !wasScanning.current) {
      dispatch({ type: "reset", key: selectionKey })
    }
    wasScanning.current = isScanning
  }, [isScanning, selectionKey])

  const selectedPaths = useMemo(
    () => (state.key === selectionKey ? state.paths : []),
    [selectionKey, state.key, state.paths],
  )
  const selectedSet = useMemo(() => new Set(selectedPaths), [selectedPaths])

  return {
    selectedPaths,
    selectedSet,
    updatePath: (path, checked) => {
      dispatch({ type: "replace", key: selectionKey, paths: [path], checked })
    },
    updatePaths: (paths, checked) => {
      dispatch({ type: "replace", key: selectionKey, paths, checked })
    },
    reset: () => dispatch({ type: "reset", key: selectionKey }),
  }
}

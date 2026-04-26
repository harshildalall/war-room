function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults || {});
  const setTweak = React.useCallback((key, value) => {
    setValues(current => ({ ...current, [key]: value }));
  }, []);
  return [values, setTweak];
}

function TweaksPanel({ children }) {
  return null;
}

function TweakSection() {
  return null;
}

function TweakRadio() {
  return null;
}


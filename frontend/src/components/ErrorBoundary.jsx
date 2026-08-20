// React error boundary: catches render errors and shows a fallback UI instead of crashing.
import React from "react";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, fontFamily: "sans-serif" }}>
          <h2 style={{ color: "#A32D2D" }}>Something went wrong</h2>
          <pre style={{
            background: "#f5f5f5", padding: 16, borderRadius: 8,
            fontSize: 12, overflow: "auto",
          }}>
            {this.state.error?.toString()}
          </pre>
          <button onClick={() => window.location.href = "/login"}>
            Back to Login
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;

import React from 'react';
import Sidebar from './Sidebar';

export default function Layout({ children }) {
  return (
    <div style={s.root}>
      <Sidebar />
      <main style={s.main}>{children}</main>
    </div>
  );
}

const s = {
  root: {
    display: 'flex',
    height: '100vh',
    fontFamily: "'Inter','Segoe UI',sans-serif",
    overflow: 'hidden',
  },
  main: {
    flex: 1,
    background: '#F0F4F8',
    overflowY: 'auto',
    padding: '36px 40px',
    boxSizing: 'border-box',
  },
};

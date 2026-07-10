// Shell layout: Sidebar on the left, page content on the right, floating AI chatbox.
import React from 'react';
import Sidebar from './Sidebar';
import AIChatbox from './AIChatbox';

export default function Layout({ children }) {
  return (
    <div style={s.root}>
      <Sidebar />
      <main style={s.main}>
        <div style={s.content}>
          {children}
        </div>
      </main>
      <AIChatbox />
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
    padding: '28px',
    boxSizing: 'border-box',
  },
  content: {
    maxWidth: 1200,
    margin: '0 auto',
  },
};

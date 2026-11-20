import React from 'react';
import { Link } from 'react-router-dom';

export default function ResetPassword() {
  return <div className="card" style={{ maxWidth: 440, margin: '40px auto' }}>
    <h2 className="oswald">Account recovery has changed</h2>
    <p>Email reset links are no longer used. Enter your email on the sign-in page, then choose Forgot password to recover with a saved recovery code.</p>
    <Link to="/login">Back to sign in</Link>
  </div>;
}

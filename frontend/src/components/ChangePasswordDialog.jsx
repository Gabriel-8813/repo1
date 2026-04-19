import React, { useState } from 'react';
import axios from 'axios';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger
} from './ui/dialog';
import { KeyRound } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Change Password button + dialog.
 * Props:
 *  - token: auth token
 *  - variant: 'ghost' | 'outline' | ... (Button variant)
 *  - size: Button size
 *  - label: optional override for the trigger label
 */
export default function ChangePasswordDialog({ token, variant = 'ghost', size = 'sm', label = 'Change Password' }) {
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const reset = () => { setCurrent(''); setNext(''); setConfirm(''); };

  const handleSubmit = async (e) => {
    e?.preventDefault?.();
    if (next !== confirm) {
      toast.error('New password and confirmation do not match');
      return;
    }
    if (next.length < 8) {
      toast.error('New password must be at least 8 characters');
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`${API}/auth/change-password`,
        { current_password: current, new_password: next },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success('Password updated — use the new password next time you log in');
      reset();
      setOpen(false);
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Password change failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) reset(); }}>
      <DialogTrigger asChild>
        <Button variant={variant} size={size} data-testid="change-password-trigger-btn">
          <KeyRound className="w-4 h-4 mr-2" /> {label}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change Password</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="current-pwd">Current password</Label>
            <Input
              id="current-pwd"
              type="password"
              value={current}
              onChange={e => setCurrent(e.target.value)}
              required
              autoComplete="current-password"
              data-testid="current-password-input"
            />
          </div>
          <div>
            <Label htmlFor="new-pwd">New password</Label>
            <Input
              id="new-pwd"
              type="password"
              value={next}
              onChange={e => setNext(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
              data-testid="new-password-input"
            />
            <p className="text-xs text-slate-400 mt-1">Minimum 8 characters</p>
          </div>
          <div>
            <Label htmlFor="confirm-pwd">Confirm new password</Label>
            <Input
              id="confirm-pwd"
              type="password"
              value={confirm}
              onChange={e => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              data-testid="confirm-password-input"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              type="submit"
              disabled={submitting || !current || !next || !confirm}
              className="bg-blue-600 hover:bg-blue-700"
              data-testid="save-password-btn"
            >
              {submitting ? 'Updating...' : 'Update Password'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

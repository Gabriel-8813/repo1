import React, { useState } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { ShieldCheck } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const PrivacyGate = () => {
  const { user, token, refreshUser } = useAuth();
  const [accepting, setAccepting] = useState(false);
  const [checked, setChecked] = useState(false);

  if (!user || !token || user.privacy_policy) return null;

  const accept = async () => {
    setAccepting(true);
    try {
      await axios.post(`${API}/auth/accept-privacy`, {}, { headers: { Authorization: `Bearer ${token}` } });
      await refreshUser();
      toast.success('Thank you — privacy policy accepted');
    } catch {
      toast.error('Could not record acceptance. Please try again.');
    } finally {
      setAccepting(false);
    }
  };

  return (
    <Dialog open>
      <DialogContent className="max-w-md [&>button.absolute]:hidden" onInteractOutside={(e) => e.preventDefault()} onEscapeKeyDown={(e) => e.preventDefault()} data-testid="privacy-gate-dialog">
        <DialogHeader>
          <DialogTitle className="font-archivo flex items-center gap-2"><ShieldCheck className="w-5 h-5 text-blue-600" /> Privacy policy update</DialogTitle>
          <DialogDescription>
            MediTrans has strengthened how personal and health-adjacent information is protected. Please review and accept our privacy policy to continue.
          </DialogDescription>
        </DialogHeader>
        <div className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3 space-y-1.5">
          <p>· Recipient personal data is encrypted at rest and in transit</p>
          <p>· Drivers see only the logistics fields needed for their delivery</p>
          <p>· SMS updates require consent and honor STOP opt-outs (CASL)</p>
          <p>· Personal data is auto-redacted after the retention period</p>
          <p>· All access is recorded in a tamper-evident audit log</p>
        </div>
        <label className="flex items-start gap-2 cursor-pointer">
          <input type="checkbox" className="mt-0.5 accent-blue-600" checked={checked} onChange={(e) => setChecked(e.target.checked)} data-testid="privacy-gate-checkbox" />
          <span className="text-xs text-slate-600">
            I have read and accept the <a href="/privacy" target="_blank" rel="noreferrer" className="text-blue-600 underline font-semibold">MediTrans Privacy Policy</a> (v1.0).
          </span>
        </label>
        <Button className="w-full rounded-full bg-blue-600 hover:bg-blue-700" disabled={!checked || accepting} onClick={accept} data-testid="privacy-gate-accept-btn">
          {accepting ? 'Saving…' : 'Accept and continue'}
        </Button>
      </DialogContent>
    </Dialog>
  );
};

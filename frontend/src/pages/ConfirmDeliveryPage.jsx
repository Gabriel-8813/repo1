import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Textarea } from '../components/ui/textarea';
import { Truck, CheckCircle2, Star } from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ConfirmDeliveryPage() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [error, setError] = useState(null);
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState('');
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    axios.get(`${API}/public/confirm/${token}`)
      .then((r) => { setInfo(r.data); if (r.data.confirmed_at) setDone(true); })
      .catch(() => setError('This confirmation link is invalid or has expired.'));
  }, [token]);

  const submit = async () => {
    setSubmitting(true);
    try {
      await axios.post(`${API}/public/confirm/${token}`, {
        rating: rating || null,
        comment: comment.trim() || null,
      });
      setDone(true);
      toast.success('Thank you — delivery confirmed!');
    } catch {
      toast.error('Could not confirm. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4" data-testid="confirm-delivery-page">
      <Card className="border-0 shadow-[0_4px_24px_rgba(0,0,0,0.08)] max-w-md w-full">
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center"><Truck className="w-5 h-5 text-white" /></div>
            <span className="font-archivo font-bold text-lg text-slate-900">MediTrans</span>
          </div>

          {error && <p className="text-sm text-red-600" data-testid="confirm-error">{error}</p>}

          {info && !done && (
            <>
              <div>
                <h1 className="text-xl font-bold text-slate-900 font-archivo">Confirm your delivery</h1>
                <p className="text-sm text-slate-500 mt-1">
                  {info.title} from <span className="font-semibold">{info.facility_name}</span>, delivered by {info.driver_first_name}
                  {info.delivered_at ? ` on ${info.delivered_at.slice(0, 10)}` : ''}.
                </p>
              </div>
              {!info.already_reviewed && (
                <div>
                  <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1.5">Rate your courier (optional)</p>
                  <div className="flex gap-1" data-testid="recipient-rating-stars">
                    {[1, 2, 3, 4, 5].map((s) => (
                      <button key={s} onClick={() => setRating(s)} onMouseEnter={() => setHover(s)} onMouseLeave={() => setHover(0)} data-testid={`star-${s}`}>
                        <Star className={`w-8 h-8 transition-colors ${(hover || rating) >= s ? 'text-amber-400 fill-amber-400' : 'text-slate-200'}`} />
                      </button>
                    ))}
                  </div>
                  {rating > 0 && (
                    <Textarea className="mt-2" placeholder="Anything to add? (optional)" value={comment} onChange={(e) => setComment(e.target.value)} data-testid="recipient-comment-input" />
                  )}
                </div>
              )}
              <Button className="w-full rounded-full bg-emerald-600 hover:bg-emerald-700 h-11 text-base" onClick={submit} disabled={submitting} data-testid="confirm-delivery-btn">
                <CheckCircle2 className="w-5 h-5 mr-2" /> {submitting ? 'Confirming…' : 'Confirm delivery received'}
              </Button>
              <p className="text-[11px] text-slate-400 text-center">Reply STOP to any MediTrans text to opt out of SMS updates.</p>
            </>
          )}

          {done && (
            <div className="text-center py-6" data-testid="confirm-thankyou">
              <CheckCircle2 className="w-14 h-14 text-emerald-500 mx-auto mb-3" />
              <h2 className="text-xl font-bold text-slate-900 font-archivo">Delivery confirmed</h2>
              <p className="text-sm text-slate-500 mt-1">Thank you! Your confirmation has been recorded.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import { useParams, useSearchParams, Link } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import StarRating from '../components/StarRating';
import {
  Heart, Truck, CheckCircle, MapPin, Sparkles, ArrowRight
} from 'lucide-react';
import { toast } from 'sonner';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TipPage = () => {
  const { jobId } = useParams();
  const [searchParams] = useSearchParams();
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(null); // preset index or 'custom'
  const [customAmount, setCustomAmount] = useState('');
  const [tipperName, setTipperName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [paidState, setPaidState] = useState(null); // null | 'checking' | 'success' | 'failed'
  const [postTipRating, setPostTipRating] = useState(0);
  const [postTipComment, setPostTipComment] = useState('');
  const [postTipSubmitting, setPostTipSubmitting] = useState(false);
  const [postTipDone, setPostTipDone] = useState(false);
  const [alreadyReviewed, setAlreadyReviewed] = useState(false);

  useEffect(() => {
    fetchInfo();
    checkReturn();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const fetchInfo = async () => {
    try {
      const r = await axios.get(`${API}/tips/info/${jobId}`);
      setInfo(r.data);
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not load trip');
    } finally {
      setLoading(false);
    }
    // Also check if trip was already reviewed (separate public endpoint)
    try {
      const rev = await axios.get(`${API}/reviews/info/${jobId}`);
      setAlreadyReviewed(!!rev.data.already_reviewed);
    } catch { /* ignore — tip page still works */ }
  };

  const submitPostTipReview = async () => {
    if (postTipRating === 0) {
      toast.error('Please select a rating');
      return;
    }
    setPostTipSubmitting(true);
    try {
      await axios.post(`${API}/reviews/${jobId}`, {
        rating: postTipRating,
        comment: postTipComment || null,
        reviewer_name: tipperName || null
      });
      setPostTipDone(true);
      toast.success('Thanks for your review!');
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not submit review');
    } finally {
      setPostTipSubmitting(false);
    }
  };

  const checkReturn = async () => {
    const sessionId = searchParams.get('session_id');
    if (!sessionId) return;
    setPaidState('checking');
    let attempts = 0;
    const maxAttempts = 6;
    const poll = async () => {
      try {
        const r = await axios.get(`${API}/tips/status/${sessionId}`);
        if (r.data.payment_status === 'paid') {
          setPaidState('success');
          return;
        }
        if (r.data.status === 'expired') {
          setPaidState('failed');
          return;
        }
        attempts++;
        if (attempts < maxAttempts) setTimeout(poll, 2000);
        else setPaidState('failed');
      } catch {
        setPaidState('failed');
      }
    };
    poll();
  };

  const getAmount = () => {
    if (selected === 'custom') return parseFloat(customAmount) || 0;
    if (typeof selected === 'number' && info) return info.presets[selected].amount;
    return 0;
  };

  const handleSendTip = async () => {
    const amount = getAmount();
    if (amount <= 0) {
      toast.error('Please choose or enter a tip amount');
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/tips/checkout/${jobId}`, {
        amount,
        origin_url: window.location.origin,
        tipper_name: tipperName || null
      });
      window.location.href = r.data.checkout_url;
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Could not start checkout');
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center px-6">
        <Card className="max-w-md w-full">
          <CardContent className="p-8 text-center">
            <h1 className="font-archivo font-bold text-2xl text-slate-900 mb-2">Trip Not Available</h1>
            <p className="text-slate-600 mb-6">{error}</p>
            <Link to="/">
              <Button variant="outline">Go to MediTrans</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (paidState === 'success') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-emerald-50 to-blue-50 flex items-center justify-center px-6 py-10">
        <Card className="max-w-md w-full shadow-xl border-0" data-testid="tip-success-card">
          <CardContent className="p-10 text-center">
            <div className="w-20 h-20 rounded-full bg-emerald-100 flex items-center justify-center mx-auto mb-6">
              <CheckCircle className="w-10 h-10 text-emerald-600" />
            </div>
            <h1 className="font-archivo font-bold text-3xl text-slate-900 mb-3">Thank you!</h1>
            <p className="text-slate-600 mb-4">
              Your tip has been sent to <span className="font-semibold">{info?.driver.first_name}</span>. They'll really appreciate it.
            </p>
            <div className="flex items-center justify-center gap-1 text-red-500 mb-6">
              {[...Array(5)].map((_, i) => <Heart key={i} className="w-5 h-5 fill-current" />)}
            </div>

            {/* Post-tip rating prompt */}
            {!alreadyReviewed && !postTipDone ? (
              <div className="border-t border-slate-200 pt-6 mt-2 text-left" data-testid="post-tip-rating-section">
                <p className="text-center text-sm text-slate-600 mb-3">
                  Mind rating {info?.driver.first_name}?
                </p>
                <div className="flex justify-center mb-4">
                  <StarRating value={postTipRating} onChange={setPostTipRating} size="md" testidPrefix="tip-rate-star" />
                </div>
                {postTipRating > 0 && (
                  <>
                    <Label htmlFor="post-tip-comment" className="text-sm">Comment (optional)</Label>
                    <Textarea
                      id="post-tip-comment"
                      placeholder="What went well?"
                      value={postTipComment}
                      onChange={e => setPostTipComment(e.target.value)}
                      rows={2}
                      className="mb-3"
                      data-testid="tip-rate-comment-input"
                    />
                    <Button
                      onClick={submitPostTipReview}
                      disabled={postTipSubmitting}
                      className="w-full rounded-full bg-blue-600 hover:bg-blue-700"
                      data-testid="tip-submit-review-btn"
                    >
                      {postTipSubmitting ? 'Submitting...' : 'Submit Review'}
                    </Button>
                  </>
                )}
              </div>
            ) : postTipDone ? (
              <div className="border-t border-slate-200 pt-6 mt-2">
                <p className="text-emerald-700 text-sm font-medium">★ Review submitted — thank you!</p>
              </div>
            ) : null}

            <div className="mt-6">
              <Link to="/">
                <Button variant="outline" className="rounded-full">
                  Back to MediTrans <ArrowRight className="w-4 h-4 ml-2" />
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const { trip, driver, presets, currency } = info;
  const amount = getAmount();

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-slate-50 to-pink-50" data-testid="tip-page">
      {/* Mini header */}
      <header className="py-6 px-6">
        <Link to="/" className="inline-flex items-center gap-2">
          <div className="w-9 h-9 bg-blue-600 rounded-lg flex items-center justify-center">
            <Truck className="w-5 h-5 text-white" />
          </div>
          <span className="font-archivo font-bold text-lg text-slate-900">MediTrans</span>
        </Link>
      </header>

      <main className="max-w-lg mx-auto px-6 pb-12">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-pink-100 rounded-full mb-4">
            <Sparkles className="w-8 h-8 text-pink-500" />
          </div>
          <h1 className="font-archivo font-bold text-3xl text-slate-900 mb-2">
            Tip {driver.first_name}
          </h1>
          <p className="text-slate-600">
            Show your appreciation for a safe medical transport.
          </p>
        </div>

        {/* Trip card */}
        <Card className="mb-6 border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]" data-testid="tip-trip-card">
          <CardContent className="p-5">
            <div className="flex items-start justify-between gap-3 mb-3">
              <h2 className="font-semibold text-slate-900">{trip.title}</h2>
              <Badge className="bg-emerald-100 text-emerald-700">Completed</Badge>
            </div>
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <MapPin className="w-4 h-4 text-slate-400" />
              <span>{trip.pickup_city} → {trip.delivery_city}</span>
            </div>
            <p className="text-xs text-slate-500 mt-2">
              Trip fee: ${trip.offered_price.toFixed(2)} {currency}
            </p>
          </CardContent>
        </Card>

        {/* Tip selection */}
        <Card className="border-0 shadow-[0_2px_8px_rgba(0,0,0,0.08)]">
          <CardContent className="p-6">
            <Label className="mb-3 block text-slate-900 font-semibold">Select a tip</Label>
            <div className="grid grid-cols-3 gap-3 mb-4">
              {presets.map((p, i) => (
                <button
                  key={i}
                  onClick={() => { setSelected(i); setCustomAmount(''); }}
                  className={`p-4 rounded-xl border-2 transition-all ${
                    selected === i
                      ? 'border-blue-600 bg-blue-50 shadow-md'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                  data-testid={`tip-preset-${i}-btn`}
                >
                  <p className="text-xs text-slate-500">{p.label}</p>
                  <p className="font-archivo font-black text-2xl text-slate-900">${p.amount.toFixed(2)}</p>
                </button>
              ))}
            </div>

            <button
              onClick={() => setSelected('custom')}
              className={`w-full p-4 rounded-xl border-2 transition-all mb-4 ${
                selected === 'custom'
                  ? 'border-blue-600 bg-blue-50 shadow-md'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
              data-testid="tip-custom-btn"
            >
              <p className="text-xs text-slate-500 text-left">Custom amount</p>
              <p className="font-semibold text-slate-700 text-left">Enter any amount</p>
            </button>

            {selected === 'custom' && (
              <div className="mb-4">
                <Label htmlFor="custom-amt">Custom tip (CAD)</Label>
                <Input
                  id="custom-amt"
                  type="number"
                  step="0.01"
                  min="1"
                  placeholder="0.00"
                  value={customAmount}
                  onChange={e => setCustomAmount(e.target.value)}
                  data-testid="tip-custom-input"
                />
              </div>
            )}

            <div className="mb-6">
              <Label htmlFor="tipper-name">Your name (optional)</Label>
              <Input
                id="tipper-name"
                placeholder="So they know who to thank"
                value={tipperName}
                onChange={e => setTipperName(e.target.value)}
                data-testid="tipper-name-input"
              />
            </div>

            <Button
              onClick={handleSendTip}
              disabled={submitting || amount <= 0}
              className="w-full rounded-full bg-blue-600 hover:bg-blue-700 text-white py-6 text-lg"
              data-testid="send-tip-btn"
            >
              <Heart className="w-5 h-5 mr-2" />
              {submitting ? 'Opening Stripe...' : amount > 0 ? `Send $${amount.toFixed(2)} Tip` : 'Choose an amount'}
            </Button>

            <p className="text-xs text-slate-500 text-center mt-4">
              100% of your tip goes to {driver.first_name}. Secure checkout by Stripe.
            </p>
          </CardContent>
        </Card>

        <div className="text-center mt-4">
          <Link to={`/rate/${jobId}`} className="text-sm text-slate-500 hover:text-blue-600 underline" data-testid="rate-only-link">
            Don't want to tip? Rate {driver.first_name} instead
          </Link>
        </div>

        {info.already_tipped_total > 0 && (
          <p className="text-xs text-slate-400 text-center mt-4">
            Previous tips on this trip: ${info.already_tipped_total.toFixed(2)} {currency}
          </p>
        )}
      </main>
    </div>
  );
};

export default TipPage;
